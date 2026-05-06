import json

MOCK_RESPONSES_CORE = {
    "idea_generator": json.dumps(
        {
            "ideas": [
                {
                    "title": "Dynamic Sparse Attention via Entropy-Gated Head Routing",
                    "description": "We propose a dynamic sparse attention mechanism that routes attention heads to either dense or sparse computation paths based on per-head entropy estimates computed from the previous layer's attention distributions. Low-entropy heads are routed to a block-sparse path with learned mask patterns, while high-entropy heads retain full softmax attention. A lightweight gating network with Gumbel-softmax reparameterization enables differentiable routing decisions. On long-document NLP benchmarks, the method achieves 2.3x wall-clock speedup with less than 0.5% accuracy degradation compared to full attention baselines.",
                    "category": "architecture",
                    "novelty_score": 7.5,
                    "feasibility_score": 8.0,
                    "impact_score": 7.8,
                    "methodology": "Implement a per-head routing gate that monitors Shannon entropy of attention distributions; use Gumbel-softmax for differentiable routing with temperature annealing; design block-sparse CUDA kernels for the sparse path; train end-to-end with a computational budget regularizer.",
                    "expected_results": "Expect 2-3x speedup on sequences >4k tokens, competitive perplexity on PG-19 and Wikitext-103, and graceful degradation to full attention when entropy is high.",
                    "required_resources": "4x A100 GPUs for pretraining, LongBench and PG-19 benchmarks.",
                    "risk_analysis": "Routing may collapse to a single path; mitigate with entropy-based warmup and auxiliary diversity loss. Sparse kernels may not be efficient on short sequences; add length-based fallback.",
                    "related_work_diff": "Unlike static sparse attention (Longformer, BigBird), our method dynamically selects sparsity per-head. Unlike adaptive computation (Universal Transformers), we route at the attention level, not the layer level.",
                    "source_paper_ids": [],
                },
                {
                    "title": "Cross-Spectral Graph-Attention for Heterogeneous Node Classification",
                    "description": "We propose a heterogeneous graph neural network that applies spectral attention filters with relation-specific Chebyshev polynomial bases. Each edge type learns its own spectral filter coefficients, enabling the model to capture relation-specific spectral patterns in the graph Laplacian. An attention mechanism across spectral coefficients from different relations selects the most informative frequency bands per node. We evaluate on heterogeneous node classification benchmarks showing 3-5% accuracy improvements over heterogeneous GNN baselines.",
                    "category": "architecture",
                    "novelty_score": 8.0,
                    "feasibility_score": 7.5,
                    "impact_score": 7.2,
                    "methodology": "Compute relation-specific normalized Laplacians for each edge type; learn Chebyshev filter coefficients per relation; apply spectral attention across coefficient sets; aggregate via relation-aware attention pooling.",
                    "expected_results": "3-5% accuracy gain on DBLP, IMDB, and ACM heterogeneous benchmarks; efficient O(kE) complexity where k is filter order and E is edge count.",
                    "required_resources": "Single A100 GPU, OGB and HGB benchmark suites, 1 week of compute time.",
                    "risk_analysis": "Relation-specific Laplacians may be ill-conditioned for sparse relations; add regularization via Laplacian smoothing. Spectral filters assume undirected graphs; extend to directed via Hermitian Laplacian.",
                    "related_work_diff": "Existing heterogeneous GNNs (RGCN, HGT) use relation-specific linear transforms in the spatial domain; we are the first to apply relation-specific spectral filtering with learned frequency selection.",
                    "source_paper_ids": [],
                },
            ]
        }
    ),
    "idea_evaluator": json.dumps(
        {
            "evaluations": [
                {
                    "idea_title": "Dynamic Sparse Attention via Entropy-Gated Head Routing",
                    "novelty_score": 7.5,
                    "feasibility_score": 8.0,
                    "impact_score": 7.8,
                    "strengths": [
                        "Per-head dynamic routing is a clean and practical contribution",
                        "Gumbel-softmax reparameterization enables end-to-end differentiability",
                    ],
                    "weaknesses": [
                        "Routing overhead may negate gains for short sequences",
                        "Evaluation is limited to NLP; unclear generalization to vision or graph domains",
                    ],
                    "recommendations": [
                        "Include a length-based hybrid mode that falls back to dense attention for short sequences",
                        "Extend evaluation to ViT on ImageNet to demonstrate cross-domain applicability",
                    ],
                },
                {
                    "idea_title": "Cross-Spectral Graph-Attention for Heterogeneous Node Classification",
                    "novelty_score": 8.0,
                    "feasibility_score": 7.5,
                    "impact_score": 7.2,
                    "strengths": [
                        "Novel application of spectral methods to heterogeneous graphs",
                        "Relation-specific spectral filters are well-motivated and mathematically clean",
                    ],
                    "weaknesses": [
                        "Computing relation-specific Laplacians may be expensive for graphs with many edge types",
                        "Hermitian Laplacian extension for directed graphs is mentioned but not detailed",
                    ],
                    "recommendations": [
                        "Benchmark against recent heterogeneous GNN baselines (Simple-HGN, HGBNN)",
                        "Provide complexity analysis comparing spectral vs spatial approaches as edge type count grows",
                    ],
                },
            ]
        }
    ),
    "reader": json.dumps(
        {
            "core_insight": "Multi-head attention can be approximated efficiently via low-rank kernel decomposition without significant loss in downstream task accuracy.",
            "problem_solved": "Reduces the quadratic self-attention computational bottleneck from O(n^2) to O(n log n) for long-sequence transformers.",
            "key_trick": "Projects query and key matrices into a random Fourier feature space whose dot product approximates the softmax kernel, enabling linear-time attention.",
            "limitations": [
                "Random feature approximation quality degrades on very short sequences where exact softmax is cheap",
                "Kernel approximation introduces bias that accumulates across deep transformer layers without corrective normalization"
            ],
            "open_questions": [
                "Can structured random projections outperform unstructured Fourier features for domain-specific vocabularies?",
                "How does the approximation interact with retrieval-augmented generation pipelines?"
            ],
            "reusable_components": [
                "Random Fourier feature projection layer for kernel approximation in any softmax-based operation",
                "Per-layer adaptive bandwidth selection for the RFF kernel based on gradient magnitude"
            ],
            "assumed_but_not_proven": [
                "The softmax kernel is sufficiently smooth to be well-approximated by low-dimensional random features across all token distributions",
                "Gradient flow through the approximated attention maps remains stable without explicit Lipschitz constraints"
            ],
        }
    ),
    "analyst": json.dumps(
        {
            "clusters": [
                {
                    "theme": "efficient attention mechanisms",
                    "paper_indices": [0, 3, 5],
                    "shared_limitations": [
                        "All methods trade approximation quality for speed, with unclear Pareto frontier",
                        "Benchmarking is inconsistent across different hardware platforms and sequence lengths"
                    ],
                    "gaps": [
                        {
                            "seed": "Adaptive rank-selection for attention approximation that dynamically adjusts kernel dimension per head and per layer based on input entropy",
                            "rationale": "Current methods use fixed approximation ranks, but attention entropy varies drastically across layers and heads, suggesting wasted computation in low-entropy heads",
                            "type": "intra_cluster",
                        },
                        {
                            "seed": "Hardware-aware co-design of sparse attention patterns with compiler-level memory scheduling for sustained throughput on heterogeneous accelerators",
                            "rationale": "Most efficient attention methods ignore memory hierarchy effects, leading to theoretical FLOP reductions that do not translate to wall-clock speedups",
                            "type": "intra_cluster",
                        },
                    ],
                },
                {
                    "theme": "graph neural network expressivity",
                    "paper_indices": [1, 2, 4],
                    "shared_limitations": [
                        "Expressivity gains from higher-order message passing come at steep memory cost",
                        "Limited evaluation on heterophilic graphs where structural assumptions break down"
                    ],
                    "gaps": [
                        {
                            "seed": "Dynamic edge-type routing in heterogeneous GNNs that learns which relation types to activate per node based on local graph topology signals",
                            "rationale": "Existing heterogeneous GNNs apply all relation types uniformly, wasting capacity on irrelevant edges for each node",
                            "type": "intra_cluster",
                        }
                    ],
                },
            ],
            "cross_cluster_gaps": [
                {
                    "seed": "Graph-structured sparse attention where the adjacency matrix defines which token pairs attend, merging GNN message-passing with efficient transformer attention",
                    "cluster_pair": ["efficient attention mechanisms", "graph neural network expressivity"],
                    "rationale": "Attention sparsity patterns in efficient transformers and message-passing neighbourhoods in GNNs are structurally identical but optimized independently",
                    "type": "cross_cluster",
                }
            ],
        }
    ),
    "connector": json.dumps(
        {
            "structural_analogy": "Random feature approximation of softmax attention is structurally analogous to spectral graph convolutions: both replace a dense pairwise operation with a low-rank decomposition whose basis functions are chosen to preserve the dominant eigenmodes of the original operator.",
            "transfer_direction": "A→B",
            "surface_similarity": 0.2,
            "idea_seed": {
                "seed": "Spectral attention transformers that learn Chebyshev polynomial filters on the attention matrix, transferring spectral GNN filter design to efficient transformer architectures",
                "rationale": "Chebyshev filters in GNNs provide controllable approximation order with O(k) complexity; applying the same principle to attention would give a tunable accuracy-efficiency knob that current linear attention methods lack",
                "novelty_signal": "Spectral methods are ubiquitous in GNNs but almost entirely absent from transformer attention design, likely because the communities use different mathematical vocabularies for what is essentially the same operator",
            },
        }
    ),
    "contrarian": json.dumps(
        {
            "contrarian_seeds": [
                {
                    "seed": "Deliberately noisy attention: injecting calibrated heteroscedastic noise into attention logits to improve generalization and adversarial robustness",
                    "challenged_assumption": "Attention weights should converge to precise, deterministic distributions during training",
                    "flipped_to": "What if optimal attention is inherently stochastic and deterministic attention overfits to spurious training correlations?",
                    "rationale": "Stochastic depth and dropout already regularize transformers by adding noise to other components; noisy attention may similarly act as an implicit ensemble and improve OOD robustness",
                    "source_papers": ["lin2023lowrank"],
                },
                {
                    "seed": "Train transformers without attention at all: replace multi-head attention with a learned fixed-size routing table that maps token embeddings to slot vectors via differentiable nearest neighbors",
                    "challenged_assumption": "Pairwise token interaction via attention is essential for transformer performance",
                    "flipped_to": "What if slot-based routing, inspired by object-centric learning, can match or exceed attention while being O(n) by construction?",
                    "rationale": "MLP-Mixer already showed that token-mixing MLPs can replace attention; routing tables could further reduce cost while adding structural inductive bias for compositional reasoning",
                    "source_papers": ["vaswani2017attention", "tolstikhin2021mlpmixer"],
                },
                {
                    "seed": "Reverse curriculum learning for graph neural networks: train on the largest, most complex graphs first, then fine-tune on small graphs",
                    "challenged_assumption": "Curriculum learning should progress from simple to complex examples",
                    "flipped_to": "What if starting with complex graphs forces the model to learn robust local aggregations early, preventing overfitting to small-graph shortcuts?",
                    "rationale": "Standard curriculum assumes simple examples build foundations, but GNNs on small graphs can exploit degree shortcuts that vanish on large graphs; reverse curriculum may prevent this",
                    "source_papers": ["zhang2022expressive"],
                },
            ]
        }
    ),
    "synthesizer": json.dumps(
        {
            "ideas": [
                {
                    "title": "Spectral-Gated Linear Attention with Adaptive Rank Selection",
                    "description": "We propose replacing standard softmax attention with a spectral filter bank operating on Chebyshev polynomial approximations of the attention matrix. The rank of the approximation is adapted per-head and per-layer via a lightweight gating network that monitors local token entropy. This combines the O(n log n) efficiency of linear attention with the tunable expressivity of spectral graph filters. We evaluate on long-document NLP benchmarks and large-scale node classification, showing 2x wall-clock speedup with less than 1% accuracy drop.",
                    "category": "architecture",
                    "methodology": "Augment each transformer layer with a rank-selection gate that computes token entropy from the previous layer's attention maps, then selects the Chebyshev filter order accordingly; train end-to-end with a sparsity-inducing regularizer on the filter coefficients.",
                    "expected_results": "Expect 2x speedup on sequences >4k tokens, competitive perplexity on PG-19 and Wikitext-103, and improved transfer to graph classification tasks due to spectral inductive bias.",
                    "required_resources": "8x A100 GPUs for pretraining, standard GLUE/LongBench benchmark suite, ogbn-arxiv graph dataset for cross-domain evaluation.",
                    "risk_analysis": "Rank-selection gate may collapse to fixed rank during training; mitigate with entropy-based warmup and auxiliary diversity loss. Spectral filters may not generalize to modalities without natural spectral structure.",
                    "source_papers": ["lin2023lowrank", "defferrard2016chebyshev", "katharopoulos2020linear"],
                    "seed_type": "gap",
                    "rationale": "Unifies two independent lines of work on efficient attention and spectral graph filtering, addressing the gap that current linear attention methods lack a principled accuracy-efficiency tradeoff mechanism.",
                },
                {
                    "title": "Stochastic Attention via Learned Heteroscedastic Perturbations",
                    "description": "We inject learned, input-dependent Gaussian noise into attention logits before softmax, where the noise variance is predicted by a small auxiliary network. At inference time, we marginalize over the noise via Monte Carlo sampling, producing an implicit attention ensemble. We show this improves OOD robustness on distribution-shifted NLP benchmarks without sacrificing in-distribution accuracy. The noise variance collapses to near-zero on easy examples and increases on ambiguous ones, providing a natural uncertainty signal.",
                    "category": "training_technique",
                    "methodology": "Add a noise-prediction head to each transformer layer that outputs per-head log-variance given the query-key dot products; reparameterize noise via the pathwise derivative trick; train with a KL regularizer that penalizes unnecessary noise.",
                    "expected_results": "Expect 1-3% accuracy improvement on OOD datasets (Hendrycks MMLU, WILDS) with no degradation on IID validation; attention entropy should correlate with prediction confidence.",
                    "required_resources": "4x A100 GPUs, standard transformer training pipeline, OOD evaluation suites.",
                    "risk_analysis": "Noise may destabilize early training; mitigate with warmup schedule and variance clamping. MC marginalization adds inference cost; investigate single-sample approximation as fallback.",
                    "source_papers": ["lin2023lowrank", "gal2016dropout"],
                    "seed_type": "contrarian",
                    "rationale": "Challenges the assumption that deterministic attention is optimal, building on dropout theory to show that stochastic attention can be a feature rather than a bug.",
                },
            ]
        }
    ),
    "critic": json.dumps(
        {
            "evaluations": [
                {
                    "idea_title": "Spectral-Gated Linear Attention with Adaptive Rank Selection",
                    "novelty_score": 7.8,
                    "feasibility_score": 7.2,
                    "impact_score": 7.5,
                    "overall_score": 7.5,
                    "direction_alignment_score": 8.0,
                    "already_done_by": None,
                    "strengths": [
                        "Clean unification of spectral filtering and linear attention that addresses a real efficiency gap",
                        "Adaptive rank selection is a practical contribution that could be adopted independently"
                    ],
                    "weaknesses": [
                        "Chebyshev filter design assumes spectral structure that may not hold for all modalities",
                        "Evaluation plan mixes NLP and graph tasks without a clear shared metric"
                    ],
                    "recommendation": "accept",
                },
                {
                    "idea_title": "Stochastic Attention via Learned Heteroscedastic Perturbations",
                    "novelty_score": 7.0,
                    "feasibility_score": 8.0,
                    "impact_score": 6.8,
                    "overall_score": 7.3,
                    "direction_alignment_score": 7.5,
                    "already_done_by": None,
                    "strengths": [
                        "Simple implementation that integrates cleanly into existing transformer codebases",
                        "Natural uncertainty calibration signal from noise variance is an elegant side benefit"
                    ],
                    "weaknesses": [
                        "MC marginalization at inference time may negate efficiency gains from linear attention",
                        "Connection between noise variance and OOD robustness needs stronger theoretical grounding"
                    ],
                    "recommendation": "weak_accept",
                },
            ]
        }
    ),
    "merger_group_synth": json.dumps(
        {
            "theme": "Efficient and robust attention via structured approximation",
            "synthesis": "This group of ideas converges on a shared insight: the dominant cost in transformer scaling stems from treating attention as an unstructured dense operation, and significant gains are available by imposing structure, whether spectral, stochastic, or adaptive. The spectral approach exploits mathematical structure in the attention operator itself, while stochastic perturbation adds beneficial noise that implicitly regularizes the learned approximation. Together they suggest a design space where approximation structure and training-time noise are jointly optimized rather than treated as independent design axes.",
            "emergent_angles": [
                "Joint optimization of spectral approximation order and stochastic perturbation magnitude per layer",
                "Using the noise variance from stochastic attention as a free energy signal to guide adaptive rank selection"
            ],
        }
    ),
    "merger_merge": json.dumps(
        {
            "ideas": [
                {
                    "title": "Spectral-Stochastic Hybrid Attention",
                    "description": "Combine Chebyshev spectral filtering with learned heteroscedastic noise injection in the spectral domain, where noise is added to the polynomial coefficients rather than the logits directly. This allows the noise to perturb the global spectral shape of attention, providing more structured regularization than logit-space noise while preserving O(n log n) efficiency.",
                    "category": "architecture",
                    "methodology": "Predict per-head noise variance for each Chebyshev coefficient via a lightweight MLP; apply reparameterized noise to coefficients before reconstructing the approximated attention map; train with coefficient-level KL regularization.",
                    "source_groups": [0, 1],
                    "seed_type": "merged",
                    "rationale": "Merging spectral structure with stochastic regularization in the coefficient space creates a single mechanism that simultaneously controls approximation quality and regularization strength, reducing the need for separate hyperparameters.",
                },
                {
                    "title": "Entropy-Gated Adaptive Sparse Attention",
                    "description": "Use per-head token entropy computed from the previous layer to dynamically select between full softmax attention, spectral Chebyshev approximation, and slot-based routing. A gating network routes each head to the cheapest sufficient attention variant, achieving compute savings proportional to the fraction of heads that can use cheaper approximations at each layer.",
                    "category": "architecture",
                    "methodology": "Train a three-way softmax gate per attention head that takes token entropy statistics as input; enforce differentiable routing via Gumbel-softmax with a temperature annealing schedule; profile wall-clock cost of each variant at each gate decision to train a cost-aware auxiliary loss.",
                    "source_groups": [0, 1],
                    "seed_type": "merged",
                    "rationale": "Rather than choosing a single approximation strategy, this merged idea recognizes that different heads and layers have different entropy profiles and should use different attention implementations, optimizing the Pareto frontier between accuracy and speed.",
                },
            ]
        }
    ),
    "merger_meta": json.dumps(
        {
            "theme": "Structured efficiency for next-generation sequence models",
            "synthesis": "Across all groups, the meta-pattern is that imposing the right kind of structure, whether spectral, stochastic, or adaptive, on attention operations yields disproportionate efficiency gains with minimal accuracy cost. The key unresolved tension is between generality and specialization: universal approximation strategies (linear attention, slot routing) sacrifice per-task performance, while highly specialized approaches (spectral filters, entropy gates) require domain-specific tuning. The most promising direction is meta-learned structure selection, where the model learns which structural inductive bias to apply based on the data, rather than requiring the practitioner to choose.",
        }
    ),
    "keyword_expander": json.dumps(
        {
            "keywords": [
                "efficient attention",
                "linear transformer",
                "kernel approximation",
                "spectral filtering",
            ],
            "sub_topics": [
                "random feature attention",
                "sparse attention patterns",
                "long-context transformers",
            ],
            "arxiv_categories": ["cs.LG", "cs.CL", "cs.AI"],
            "semantic_scholar_queries": [
                "linear attention kernel approximation transformer",
                "spectral graph neural network attention efficiency",
            ],
            "arxiv_queries": [
                "all:efficient AND all:attention AND all:transformer",
                "all:linear AND all:attention AND all:kernel AND all:approximation",
            ],
            "related_terms": [
                "performer",
                "linear transformer",
                "flash attention",
                "sparse transformer",
            ],
            "research_threads": [
                "random feature methods for softmax kernel approximation",
                "hardware-aware sparse attention design",
            ],
            "expanded_direction": {
                "name": "Structured Efficient Attention Mechanisms",
                "description": "Exploring mathematically structured approximations to softmax attention, including spectral methods, kernel methods, and adaptive sparsity, with a focus on provable approximation bounds and practical wall-clock efficiency on modern accelerators.",
                "keywords": ["structured attention", "spectral transformer", "adaptive sparsity"],
                "sub_topics": ["Chebyshev attention filters", "entropy-gated routing", "hardware co-design"],
                "depth": "explore",
            },
        }
    ),
    "direction_filter": json.dumps(
        {
            "scores": [
                {
                    "index": 0,
                    "relevance": 0.88,
                    "reason": "Directly addresses efficient attention mechanisms via structured approximation, which is the core topic of the research direction.",
                },
                {
                    "index": 1,
                    "relevance": 0.72,
                    "reason": "Covers graph neural network expressivity which is tangentially related through shared spectral methods but not the primary focus.",
                },
                {
                    "index": 2,
                    "relevance": 0.55,
                    "reason": "Discusses general transformer optimization techniques that could apply but lack specific connection to structured attention approximation.",
                },
            ]
        }
    ),
    "idea_extractor_innovations": json.dumps(
        {
            "innovations": [
                {
                    "title": "Adaptive Spectral Attention with Entropy-Gated Rank Selection",
                    "description": "A novel attention mechanism that dynamically selects the rank of spectral approximation per attention head based on the entropy of the previous layer's attention distribution, achieving O(n log n) complexity with tunable accuracy.",
                    "innovation_type": "architecture",
                    "confidence": 0.92,
                    "location": "Section 3.2",
                },
                {
                    "title": "Heteroscedastic Noise Injection for Attention Regularization",
                    "description": "A training technique that injects input-dependent Gaussian noise into attention logits with learned variance, creating an implicit attention ensemble that improves out-of-distribution robustness without sacrificing in-distribution accuracy.",
                    "innovation_type": "method",
                    "confidence": 0.85,
                    "location": "Section 4.1",
                },
            ]
        }
    ),
    "idea_extractor_methods": json.dumps(
        {
            "methods": [
                {
                    "name": "Chebyshev Spectral Attention",
                    "description": "Approximates softmax attention using Chebyshev polynomial filters on the query-key similarity matrix, providing controllable approximation order with linear complexity in sequence length.",
                    "key_components": [
                        "Chebyshev polynomial basis selection",
                        "per-head filter coefficient learning",
                        "adaptive order selection gate",
                    ],
                    "inputs": ["query tensor Q", "key tensor K", "value tensor V"],
                    "outputs": ["approximated attention output", "filter order per head"],
                    "differences_from_prior": [
                        "Uses orthogonal polynomial basis instead of random features, giving provable convergence bounds",
                        "Filter order is adaptive rather than fixed, allowing per-head accuracy-efficiency tradeoffs"
                    ],
                },
                {
                    "name": "Stochastic Logit Perturbation",
                    "description": "Adds learned heteroscedastic Gaussian noise to attention logits before softmax, where noise variance is predicted by an auxiliary network conditioned on query-key dot products.",
                    "key_components": [
                        "noise variance prediction head",
                        "reparameterized noise sampling",
                        "KL divergence regularization on noise magnitude",
                    ],
                    "inputs": ["attention logits", "query-key similarity matrix"],
                    "outputs": ["perturbed attention weights", "predicted noise variance"],
                    "differences_from_prior": [
                        "Noise is input-dependent rather than fixed-variance, concentrating regularization where the model is uncertain",
                        "Variance prediction provides a free uncertainty signal without additional forward passes"
                    ],
                },
            ]
        }
    ),
    "idea_extractor_scenarios": json.dumps(
        {
            "scenarios": [
                {
                    "large_scenario": "natural language processing",
                    "small_scenario": "long-document summarization",
                    "extendable_scenarios": [
                        "legal contract analysis",
                        "scientific paper summarization",
                        "multi-chapter book understanding",
                    ],
                    "data_type": "text",
                    "task_type": "summarization",
                },
                {
                    "large_scenario": "graph machine learning",
                    "small_scenario": "node classification on citation networks",
                    "extendable_scenarios": [
                        "knowledge graph completion",
                        "molecular property prediction",
                        "social network community detection",
                    ],
                    "data_type": "graph",
                    "task_type": "classification",
                },
            ]
        }
    ),
    "idea_extractor_techniques": json.dumps(
        {
            "techniques": [
                {
                    "name": "Entropy-Gated Rank Selection",
                    "category": "adaptive_computation",
                    "description": "Computes the Shannon entropy of attention distributions from the previous layer and uses it to gate the rank of spectral approximation in the current layer, reducing rank for low-entropy heads where precise attention is less critical.",
                    "formula": None,
                },
                {
                    "name": "Coefficient-Level Stochastic Perturbation",
                    "category": "regularization",
                    "description": "Injects learned Gaussian noise into the Chebyshev polynomial coefficients of spectral attention, perturbing the global spectral shape of attention maps for implicit regularization rather than perturbing individual token interactions.",
                    "formula": None,
                },
            ]
        }
    ),
}
