import json

MOCK_RESPONSES_ANALYSIS = {
    "ablation_analyzer": json.dumps(
        {
            "components": [
                {
                    "component": "multi-head attention",
                    "contribution": 22.5,
                    "baseline_performance": 76.0,
                    "without_performance": 53.5,
                    "with_performance": 76.0,
                },
                {
                    "component": "residual connection",
                    "contribution": 15.0,
                    "baseline_performance": 76.0,
                    "without_performance": 61.0,
                    "with_performance": 76.0,
                },
                {
                    "component": "layer normalization",
                    "contribution": 8.5,
                    "baseline_performance": 76.0,
                    "without_performance": 67.5,
                    "with_performance": 76.0,
                },
                {
                    "component": "positional encoding",
                    "contribution": 5.0,
                    "baseline_performance": 76.0,
                    "without_performance": 71.0,
                    "with_performance": 76.0,
                },
            ],
            "sensitivity_analysis": {
                "most_critical": "multi-head attention",
                "least_critical": "positional encoding",
                "interaction_effects": "Removing both attention and residual together drops accuracy to 38%, suggesting synergistic dependency.",
            },
            "key_insights": [
                "Multi-head attention is the most critical component, contributing 22.5% absolute accuracy",
                "Residual connections are essential for training deep variants (>6 layers)",
                "Layer normalization has moderate impact but stabilizes training convergence",
                "Positional encoding has the smallest individual impact but is crucial for sequence-order-sensitive tasks",
            ],
            "summary": "Multi-head attention and residual connections are the two most critical components, jointly accounting for 37.5% of model performance. The model is most sensitive to the removal of attention mechanisms.",
        }
    ),
    "idea_reviewer": json.dumps(
        {
            "novelty_score": 7.5,
            "feasibility_score": 8.0,
            "impact_score": 7.8,
            "overall_score": 7.8,
            "critiques": [
                {
                    "critique_id": "critique_1",
                    "aspect": "novelty",
                    "severity": "minor",
                    "description": "The dynamic routing mechanism is similar to mixture-of-experts routing but applied at the attention head level.",
                    "suggestion": "Clearly articulate how per-head entropy-based routing differs from MoE routing and what advantages the attention-level granularity provides.",
                },
                {
                    "critique_id": "critique_2",
                    "aspect": "feasibility",
                    "severity": "minor",
                    "description": "Block-sparse CUDA kernels require significant engineering effort and may not be portable across GPU architectures.",
                    "suggestion": "Consider using existing sparse kernel libraries (e.g., Triton) to reduce implementation overhead and improve portability.",
                },
            ],
            "summary": "A promising idea with strong novelty in applying dynamic routing to attention heads. The entropy-based gating is well-motivated. Main concern is engineering complexity of sparse kernels, but the fallback mechanism mitigates this risk.",
        }
    ),
    "hypothesis": json.dumps(
        {
            "hypotheses": [
                {
                    "statement": "Incorporating sparse attention patterns into graph neural networks will reduce computational complexity from O(n^2) to O(n log n) while maintaining at least 95% of the original model's predictive accuracy on molecular property prediction tasks.",
                    "rationale": "Sparse attention has proven effective in transformer architectures for NLP, and graph-structured data exhibits inherent sparsity that could benefit from similar mechanisms without loss of expressive power.",
                    "testability": "Implement sparse attention GNN variants on standard benchmarks (OGBG-MolPCBA, ZINC) and compare F1 scores and inference latency against dense attention baselines.",
                    "source_papers": ["vaswani2017attention", "ying2021transformer"],
                    "predicted_outcome": "Sparse attention GNN will achieve comparable accuracy (within 2% F1) while reducing memory usage by 40-60% on large molecular graphs with >500 nodes.",
                    "required_experiment": "Train GIN and GraphSAGE models with sparse attention heads on OGBG-MolPCBA using 10-fold cross-validation, measuring accuracy, memory consumption, and wall-clock training time against dense baselines.",
                    "confidence": 0.78,
                },
                {
                    "statement": "Multi-scale feature aggregation in vision transformers, where patch embeddings from layers 4, 8, and 12 are fused via learned gating weights, will improve object detection AP by at least 3 points on COCO when used as a backbone for Mask R-CNN.",
                    "rationale": "Feature Pyramid Networks demonstrated that multi-scale representations are critical for detection, yet standard ViT architectures discard intermediate layer features that capture different levels of abstraction.",
                    "testability": "Modify a ViT-Base backbone to output concatenated multi-scale features, integrate with Mask R-CNN, and evaluate AP50 and AP75 on COCO val2017 against single-scale ViT and ResNet-101 FPN baselines.",
                    "source_papers": ["dosovitskiy2021image", "lin2017feature"],
                    "predicted_outcome": "Multi-scale ViT backbone will yield AP improvements of 3-5 points on small object detection while maintaining competitive performance on medium and large objects.",
                    "required_experiment": "Pre-train ViT-Base on ImageNet-21K, fine-tune multi-scale adapter layers on COCO train2017, and benchmark detection and instance segmentation metrics against published ViTDet and ResNet FPN numbers.",
                    "confidence": 0.72,
                },
            ]
        }
    ),
    "evidence": json.dumps(
        {
            "evidence_items": [
                {
                    "paper_title": "Scaling Laws for Neural Language Models",
                    "stance": "supporting",
                    "evidence_description": "Kaplan et al. demonstrate that model performance scales predictably as a power law with respect to parameter count, data size, and compute budget, providing empirical grounding for the hypothesis that larger attention-based architectures yield consistent improvements.",
                    "strength": "strong",
                    "relevance": 0.85,
                },
                {
                    "paper_title": "Training Compute-Optimal Large Language Models",
                    "stance": "mixed",
                    "evidence_description": "Hoffmann et al. show that many models are under-trained relative to their parameter count, suggesting that the relationship between scale and performance is more nuanced than simple power laws and depends heavily on data quality and training duration.",
                    "strength": "moderate",
                    "relevance": 0.72,
                },
            ],
            "overall_assessment": "The evidence broadly supports the effectiveness of scaling attention-based architectures, but highlights important subtleties around compute-optimal training and data curation that must be accounted for in experimental design.",
        }
    ),
    "meta_analysis": json.dumps(
        {
            "trends": [
                {
                    "trend_name": "Mixture-of-Experts in Dense Architectures",
                    "description": "Growing adoption of sparse MoE layers within transformer backbones to scale model capacity without proportionally increasing inference cost, replacing or augmenting standard feed-forward blocks with routed expert subnetworks.",
                    "supporting_papers": ["fedus2022switch", "lepikhin2020gshard"],
                    "growth_rate": "increasing",
                    "related_gaps": ["Optimal expert count and routing strategies for domain-specific tasks remain under-explored"],
                },
                {
                    "trend_name": "Self-Supervised Pre-Training for Graph Learning",
                    "description": "Masked feature reconstruction and contrastive objectives adapted from NLP and vision are increasingly applied to graph neural networks, enabling strong transfer learning performance without task-specific labels.",
                    "supporting_papers": ["hou2022graphmae", "xie2022self"],
                    "growth_rate": "increasing",
                    "related_gaps": ["Theoretical understanding of why certain pretext tasks transfer better to downstream graph classification is limited"],
                },
            ],
            "gaps": [
                {
                    "gap_description": "No standardized benchmark exists for evaluating long-range dependency modeling in sequence models beyond language, particularly for time-series and spatiotemporal domains.",
                    "domain": "sequence_modeling",
                    "evidence_papers": ["tay2020long"],
                    "opportunity_score": 0.82,
                },
                {
                    "gap_description": "Adversarial robustness of graph neural networks against perturbed graph structure is poorly understood, with most defenses evaluated only on small citation networks.",
                    "domain": "graph_learning",
                    "evidence_papers": ["zugner2018adversarial"],
                    "opportunity_score": 0.73,
                },
            ],
        }
    ),
    "replication": json.dumps(
        {
            "claimed_result": "The proposed sparse-attention transformer achieves state-of-the-art perplexity of 18.1 on WikiText-103 while using 50% less memory than a dense transformer of equivalent depth.",
            "reproduction_issues": [
                {
                    "issue": "The paper does not specify the random seed or the exact number of warmup steps used in the cosine learning rate schedule, making it difficult to reproduce the reported perplexity within confidence intervals.",
                    "impact": "high",
                },
                {
                    "issue": "The sparse attention pattern relies on a custom CUDA kernel that is only compatible with compute capability 7.0+, limiting reproducibility on older GPU architectures.",
                    "impact": "medium",
                },
            ],
            "missing_details": [
                "Exact batch size per GPU and gradient accumulation steps for distributed training",
                "Initialization scheme for the learnable routing weights in the sparse attention module",
            ],
            "suggested_experiments": [
                "Run an ablation comparing uniform sparse attention versus the learned routing variant across 5 random seeds to isolate the contribution of the routing mechanism"
            ],
            "potential_improvements": [
                "Replace the hand-crafted routing heuristic with a differentiable top-k operator to enable end-to-end training of the sparsity pattern"
            ],
        }
    ),
    "transfer": json.dumps(
        {
            "transfers": [
                {
                    "method_name": "Relative Position Encoding from Music Transformers",
                    "method_description": "A continuous relative position encoding scheme that represents distances as learned continuous functions rather than fixed discrete embeddings, originally designed for capturing temporal structure in polyphonic music sequences.",
                    "transfer_rationale": "Continuous relative encodings capture fine-grained positional relationships that discrete sinusoidal embeddings miss, which could benefit vision transformers where spatial distances between patches vary continuously with image resolution.",
                    "adaptation_needed": "Extend the 1-D temporal distance function to a 2-D spatial distance over patch grids and modify the attention bias computation to handle varying input resolutions at inference time.",
                    "feasibility_score": 0.65,
                    "source_papers": ["huang2018music"],
                },
                {
                    "method_name": "Curriculum Learning from Neural Machine Translation",
                    "method_description": "A training strategy that orders training examples by difficulty score, gradually increasing complexity from short simple sentences to long syntactically complex ones, improving convergence speed and final BLEU scores.",
                    "transfer_rationale": "Graph classification tasks exhibit similar difficulty variance based on graph size and edge density; curriculum-based training could accelerate convergence when fine-tuning GNNs on multi-scale graph benchmarks.",
                    "adaptation_needed": "Define a graph difficulty metric combining node count, diameter, and label entropy, then implement a pacing function that gradually introduces harder graphs during the pre-training and fine-tuning phases.",
                    "feasibility_score": 0.72,
                    "source_papers": ["platanios2019competence"],
                },
            ]
        }
    ),
    "critique": json.dumps(
        {
            "critiques": [
                {
                    "claim": "The proposed method outperforms all baselines on GLUE benchmark, demonstrating superior generalization across diverse NLP tasks.",
                    "flaw": "The comparison uses non-reproduced baseline numbers from original papers trained on different data splits and hyperparameter configurations, introducing systematic unfairness in the evaluation.",
                    "severity": "major",
                    "suggested_improvement": "Re-train all baselines under identical hyperparameter budgets and data splits, or use a standardized evaluation framework such as the one provided by the Hugging Face Eval library.",
                    "evidence": "When Dodge et al. (2020) re-ran BERT fine-tuning with 40 random seeds per task, they observed rank reversals between models on several GLUE subtasks, demonstrating that single-seed comparisons are unreliable.",
                },
                {
                    "claim": "Our linear-time attention mechanism achieves identical accuracy to standard softmax attention on image classification.",
                    "flaw": "The claim relies on evaluation only on CIFAR-10 and CIFAR-100, which are small-scale datasets where even simple models saturate performance, masking potential accuracy degradation on more demanding benchmarks.",
                    "severity": "critical",
                    "suggested_improvement": "Extend evaluation to ImageNet-1K at minimum and report metrics on long-sequence tasks such as ImageNet-21K or high-resolution dense prediction to stress-test the approximation quality.",
                    "evidence": "Prior linear attention methods such as Performer and Linear Transformer showed less than 1% degradation on CIFAR-100 but 3-7% drops on ImageNet, consistent with approximation errors accumulating over longer sequences.",
                },
            ]
        }
    ),
    "theory": json.dumps(
        {
            "improvements": [
                {
                    "original_assumption": "The generalization gap between training and test loss in over-parameterized transformers is bounded by a constant independent of sequence length.",
                    "theoretical_issue": "Recent work on neural tangent kernels for attention shows that the generalization bound scales logarithmically with sequence length due to the softmax normalization, contradicting the constant-bound assumption.",
                    "proposed_correction": "Replace the constant generalization gap with a O(log n / sqrt(m)) bound where n is sequence length and m is model width, derived under the NTK regime for multi-head attention.",
                    "mathematical_sketch": "Let L_train and L_test denote empirical risks. Under NTK linearization, the Rademacher complexity of the attention function class scales as O(sqrt(H * d_k * log n) / sqrt(m)), giving a generalization bound of O(log n / sqrt(m)) per head where H is the number of heads and d_k is the key dimension.",
                    "impact_assessment": "This correction implies that simply increasing sequence length at fixed model width will degrade generalization, providing principled guidance for the width-depth-sequence-length trade-off in model design.",
                },
                {
                    "original_assumption": "Message-passing GNNs are as expressive as the Weisfeiler-Leman graph isomorphism test.",
                    "theoretical_issue": "The equivalence holds only for injective aggregation functions with sufficient hidden dimensions; in practice, mean or max pooling aggregators used in popular architectures strictly reduce expressiveness below the WL limit.",
                    "proposed_correction": "Characterize expressiveness as a spectrum parametrized by aggregation type and hidden dimension, providing explicit bounds for each commonly used aggregator rather than the binary WL-equivalent claim.",
                    "mathematical_sketch": "For a GNN with mean aggregation and hidden dimension d, the distinguishable fraction of k-regular graphs of size n is bounded by 1 - O(n^{-d/2}), whereas max aggregation achieves 1 - O(n^{-d}) under the same conditions, both strictly below the injective case.",
                    "impact_assessment": "Practitioners can make informed trade-offs between computational cost and expressiveness by selecting aggregators matched to the structural complexity of their target graph distributions.",
                },
            ]
        }
    ),
    "follow_up": json.dumps(
        {
            "follow_ups": [
                {
                    "future_work_claim": "The authors propose extending their efficient attention mechanism to multi-modal inputs combining text, image, and audio.",
                    "extension_idea": "Design modality-specific sparse attention patterns where cross-attention blocks use learned modality masks that dynamically route tokens from each modality to specialized expert heads, reducing cross-modal interference while preserving fusion capacity.",
                    "feasibility": "medium",
                    "novelty_assessment": "Modality-routed sparse attention is relatively unexplored; existing multi-modal transformers such as Perceiver and BEiT-3 use dense cross-attention, so sparse routing would be a meaningful architectural contribution.",
                    "required_resources": "4-8 A100 GPUs for pre-training on a combined dataset of LAION-5B image-text pairs and AudioSet audio clips, estimated 2-3 weeks of compute time.",
                },
                {
                    "future_work_claim": "The paper suggests that their contrastive graph pre-training objective could be improved with harder negative samples.",
                    "extension_idea": "Implement an adversarial negative mining strategy where a small auxiliary network generates structurally perturbed hard negatives on-the-fly during contrastive training, adapting difficulty to the current encoder capability.",
                    "feasibility": "high",
                    "novelty_assessment": "Adversarial hard negative mining is well-studied in vision contrastive learning but has seen limited application to graph contrastive methods, where structural perturbations offer a distinct and novel challenge.",
                    "required_resources": "Single A100 GPU for training on standard graph benchmarks (ZINC, OGBG-MolPCBA), approximately 3-5 days of compute time.",
                },
            ]
        }
    ),
    "adversarial": json.dumps(
        {
            "failure_cases": [
                {
                    "method_description": "A vision transformer trained with global average pooling for image classification on ImageNet.",
                    "failure_scenario": "An adversary applies patch-based adversarial perturbations to a small localized region of the image, exploiting the fact that global average pooling dilutes the signal from any single patch token.",
                    "why_it_fails": "Global average pooling uniformly aggregates all patch tokens including the adversarially perturbed ones, but the attention weights assigned to the perturbed patch remain near-uniform, preventing the classifier from isolating and down-weighting the corrupted region.",
                    "counter_example": "A 32x32 adversarial patch placed in the corner of a dog image causes the model to predict 'oven' with 0.94 confidence while the model's attention map shows near-uniform weighting across all 196 patches.",
                    "suggested_fix": "Replace global average pooling with a learned attention-based pooling head that can dynamically re-weight patch contributions, and augment training with adversarial patch examples to encourage robustness.",
                },
                {
                    "method_description": "A graph neural network using message passing for node classification on citation networks.",
                    "failure_scenario": "An adversary adds a small number of carefully chosen edges between nodes of different classes, causing misclassification cascades through the message-passing propagation.",
                    "why_it_fails": "Message-passing GNNs aggregate neighbor features without distinguishing between original and adversarially inserted edges, so a few malicious connections can inject misleading class signals that propagate across multiple hops.",
                    "counter_example": "Adding just 5 edges from high-degree CS papers to statistics papers in the Cora dataset reduces micro-F1 from 0.84 to 0.61, with misclassifications spreading up to 3 hops from each adversarial edge.",
                    "suggested_fix": "Incorporate edge confidence scores learned jointly with node representations, and apply edge dropout proportional to learned uncertainty during message passing to reduce susceptibility to injected edges.",
                },
            ]
        }
    ),
    "limitation": json.dumps(
        {
            "extensions": [
                {
                    "stated_limitation": "The method is evaluated exclusively on English-language text and may not generalize to morphologically rich or low-resource languages.",
                    "extension_direction": "Cross-lingual transfer for morphologically rich languages",
                    "proposed_approach": "Augment the pre-training corpus with a balanced sample from 20 typologically diverse languages and introduce subword regularization via BPE-dropout during fine-tuning to improve robustness to morphological variation.",
                    "expected_contribution": "Demonstrating consistent performance across typologically diverse languages would establish the method as a language-agnostic approach and open applications in multilingual information extraction.",
                    "difficulty": "medium",
                },
                {
                    "stated_limitation": "The proposed training technique requires gradient checkpointing and is memory-intensive for sequences exceeding 4096 tokens.",
                    "extension_direction": "Memory-efficient training for ultra-long sequences",
                    "proposed_approach": "Replace gradient checkpointing with selective layer-wise recomputation guided by a cost model that estimates per-layer memory savings versus recomputation overhead, combined with block-wise sequence processing that accumulates gradients over overlapping windows.",
                    "expected_contribution": "Enabling training on sequences of 32K+ tokens within a single GPU memory budget would unlock applications in long-document summarization, genomics, and code understanding without requiring model parallelism.",
                    "difficulty": "hard",
                },
            ]
        }
    ),
    "surveyor": json.dumps(
        {
            "summary": "The literature on efficient transformer architectures has converged around three main strategies: sparse attention patterns, low-rank kernel approximations, and token pruning or merging. While each approach offers distinct computational trade-offs, recent hybrid methods that combine sparse routing with recurrent state compression show the most promise for scaling to million-token contexts without sacrificing task performance.",
            "key_papers": [
                "Efficient Transformers: A Survey",
                "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
                "Longformer: The Long-Document Transformer",
            ],
            "research_threads": [
                "Hardware-aware attention implementations that minimize memory hierarchy bottlenecks",
                "Adaptive computation methods that allocate varying FLOPs per token based on input difficulty",
            ],
            "open_problems": [
                "Theoretical trade-off between approximation quality and wall-clock speed for sub-quadratic attention is not well characterized",
                "Efficient fine-tuning of long-context models without incurring quadratic memory in the backward pass",
            ],
            "trend_analysis": "The field is shifting from approximate attention toward hardware-aligned exact attention (e.g., FlashAttention, RingAttention), driven by the observation that memory bandwidth, not FLOPs, is the primary bottleneck on modern accelerators.",
        }
    ),
    "scout_query": json.dumps(
        {
            "queries": [
                "efficient sparse attention mechanisms for long-context transformer models 2023 2024",
                "mixture of experts routing strategies large language model scaling",
                "graph neural network pre-training molecular property prediction benchmarks",
            ]
        }
    ),
    "scout_analysis": json.dumps(
        {
            "related_work": "Several recent works explore sparse attention with learned routing, including Routing Transformers and Longformers with adaptive window sizes, but none combine dynamic routing with hardware-aware memory management for sub-linear scaling.",
            "novelty_validation": "The proposed idea of integrating differentiable routing into a hardware-aware sparse attention framework is novel; existing work either focuses on routing quality or hardware efficiency but not both simultaneously.",
            "innovation_gaps": [
                "No existing method jointly optimizes routing decisions for both approximation quality and GPU memory access patterns",
                "Benchmarking of sparse attention methods on heterogeneous multi-scale inputs remains limited to NLP, ignoring vision and graph domains",
            ],
            "references_needed": [
                "Roy et al., Efficient Content-Based Sparse Attention with Routing Transformers, TACL 2021",
                "Dao et al., FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning, ICLR 2024",
            ],
        }
    ),
    "refiner": json.dumps(
        {
            "title": "Hardware-Aware Dynamic Sparse Attention with Learned Routing for Multi-Domain Transformers",
            "description": "We propose a sparse attention framework that jointly learns routing decisions and memory access patterns to achieve sub-quadratic complexity on modern GPU architectures. The method uses a lightweight routing network that selects a variable number of attention heads per token while a hardware-aware scheduler maps these decisions to efficient memory operations, enabling training on sequences up to 128K tokens on a single A100 GPU.",
            "category": "architecture",
            "methodology": "Develop a differentiable top-k routing layer that selects active attention heads per token based on learned importance scores. Pair this with a CUDA kernel that compiles routing decisions into block-sparse memory accesses optimized for GPU shared memory and L2 cache behavior.",
            "expected_results": "Target perplexity within 2% of dense FlashAttention-2 on WikiText-103 and PG-19 while reducing peak memory by 3x and achieving 2x wall-clock speedup on sequences exceeding 32K tokens.",
            "required_resources": "4 A100-80GB GPUs for pre-training, 1 GPU for fine-tuning evaluations, approximately 3 weeks of total compute time across all experiments.",
            "risk_analysis": "Primary risk is that routing overhead negates memory savings for short sequences below 4K tokens. Mitigation includes a hybrid mode that falls back to dense attention when sequence length is below a learned threshold.",
            "rationale": "This refinement combines the two most promising directions in efficient attention, learned sparsity and hardware-aware memory management, into a single unified framework that addresses the limitations of each individual approach.",
            "source_papers": ["dao2023flashattention2", "roy2021routing"],
        }
    ),
}
