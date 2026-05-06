import math
import random
from typing import List, Optional, Tuple

from .models import (
    ChaosLevel,
    CHAOS_NOISE_SCALE,
    RandomnessMode,
    VectorSeed,
)


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-12:
        return vec
    return [v / norm for v in vec]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def generate_random_unit_vector(dim: int) -> List[float]:
    vec = [random.gauss(0, 1) for _ in range(dim)]
    return _normalize(vec)


def generate_random_vectors(dim: int, count: int) -> List[List[float]]:
    return [generate_random_unit_vector(dim) for _ in range(count)]


def perturb_vector(
    base_vector: List[float],
    chaos_level: ChaosLevel = ChaosLevel.MEDIUM,
    scale: Optional[float] = None,
) -> List[float]:
    if scale is None:
        scale = CHAOS_NOISE_SCALE[chaos_level]
    dim = len(base_vector)
    noise = [random.gauss(0, scale) for _ in range(dim)]
    perturbed = [base + n for base, n in zip(base_vector, noise)]
    return _normalize(perturbed)


def interpolate_vectors(
    vec_a: List[float],
    vec_b: List[float],
    alpha: float = 0.5,
) -> List[float]:
    interpolated = [
        (1 - alpha) * a + alpha * b for a, b in zip(vec_a, vec_b)
    ]
    return _normalize(interpolated)


def create_seed_full_random(
    dim: int,
    chaos_level: ChaosLevel = ChaosLevel.MEDIUM,
) -> VectorSeed:
    vec = generate_random_unit_vector(dim)
    return VectorSeed(
        vector=vec,
        source="random",
        source_description="Fully random unit vector",
        mode=RandomnessMode.FULL_RANDOM,
        noise_scale=0.0,
    )


def create_seed_perturbation(
    base_vector: List[float],
    source_description: str = "",
    chaos_level: ChaosLevel = ChaosLevel.MEDIUM,
    scale: Optional[float] = None,
) -> VectorSeed:
    if scale is None:
        scale = CHAOS_NOISE_SCALE[chaos_level]
    perturbed = perturb_vector(base_vector, chaos_level, scale)
    return VectorSeed(
        vector=perturbed,
        source="perturbation",
        source_description=source_description,
        mode=RandomnessMode.SEMANTIC_PERTURBATION,
        noise_scale=scale,
    )


def create_seeds_interpolation(
    vec_a: List[float],
    vec_b: List[float],
    desc_a: str = "",
    desc_b: str = "",
    num_steps: int = 3,
) -> List[VectorSeed]:
    seeds = []
    for i in range(1, num_steps + 1):
        alpha = i / (num_steps + 1)
        interp = interpolate_vectors(vec_a, vec_b, alpha)
        seeds.append(
            VectorSeed(
                vector=interp,
                source="interpolation",
                source_description=f"Interpolation(alpha={alpha:.2f}) between '{desc_a}' and '{desc_b}'",
                mode=RandomnessMode.INTERPOLATION,
                noise_scale=alpha,
            )
        )
    return seeds


def batch_create_seeds(
    mode: RandomnessMode,
    dim: int,
    count: int,
    chaos_level: ChaosLevel = ChaosLevel.MEDIUM,
    base_vectors: Optional[List[Tuple[List[float], str]]] = None,
) -> List[VectorSeed]:
    seeds = []
    if mode == RandomnessMode.FULL_RANDOM:
        for _ in range(count):
            seeds.append(create_seed_full_random(dim, chaos_level))

    elif mode == RandomnessMode.SEMANTIC_PERTURBATION:
        if not base_vectors:
            for _ in range(count):
                seeds.append(create_seed_full_random(dim, chaos_level))
        else:
            for i in range(count):
                base_vec, desc = base_vectors[i % len(base_vectors)]
                seeds.append(
                    create_seed_perturbation(base_vec, desc, chaos_level)
                )

    elif mode == RandomnessMode.INTERPOLATION:
        if base_vectors and len(base_vectors) >= 2:
            for i in range(count):
                idx_a = random.randint(0, len(base_vectors) - 1)
                idx_b = random.randint(0, len(base_vectors) - 1)
                if idx_b == idx_a:
                    idx_b = (idx_a + 1) % len(base_vectors)
                vec_a, desc_a = base_vectors[idx_a]
                vec_b, desc_b = base_vectors[idx_b]
                interp_seeds = create_seeds_interpolation(
                    vec_a, vec_b, desc_a, desc_b, num_steps=1
                )
                seeds.extend(interp_seeds)
        else:
            for _ in range(count):
                seeds.append(create_seed_full_random(dim, chaos_level))

    return seeds[:count]
