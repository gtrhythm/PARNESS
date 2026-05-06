"""Prompt 模板定义

为4种提取维度定义 System Prompt 和 User Prompt。
所有 Prompt 要求 LLM 输出结构化 JSON，便于解析。
"""

INNOVATION_SYSTEM_PROMPT = (
    "You are an expert research assistant specializing in analyzing "
    "academic papers and identifying their novel contributions and innovations. "
    "You extract structured information about the paper's innovations."
)

INNOVATION_USER_PROMPT = (
    "Analyze the following paper content and extract ALL innovations/contributions "
    "claimed by the authors.\n\n"
    "For each innovation, provide:\n"
    '- "title": A short descriptive name for the innovation '
    '(e.g., "Dynamic Token Pruning Mechanism")\n'
    '- "description": A detailed description of what the innovation is and how it works '
    "(2-4 sentences)\n"
    '- "innovation_type": Classify as one of: "architecture", "method", "scenario", '
    '"data", "loss_function", "training_trick", "other"\n'
    '- "confidence": Your confidence score 0.0-1.0 that this is a genuine novel '
    "contribution (not incremental)\n"
    '- "location": Where in the paper this innovation is primarily described '
    '(e.g., "Section 3.2")\n\n'
    "Rules:\n"
    "- Focus on genuinely novel contributions, not standard techniques or minor variations\n"
    "- Each innovation should be distinct and non-overlapping\n"
    "- Be generous in extraction but strict in confidence scoring\n\n"
    'Output a JSON object with a single key "innovations" containing an array:\n'
    "```json\n"
    "{\n"
    '  "innovations": [\n'
    "    {\n"
    '      "title": "...",\n'
    '      "description": "...",\n'
    '      "innovation_type": "...",\n'
    '      "confidence": 0.0,\n'
    '      "location": "..."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "Paper content:\n---\n{content}\n---"
)

METHOD_SYSTEM_PROMPT = (
    "You are an expert research assistant specializing in analyzing "
    "technical methods and algorithms in academic papers. "
    "You extract structured information about the paper's methodology."
)

METHOD_USER_PROMPT = (
    "Analyze the following paper content and extract the main methods and algorithms "
    "proposed by the authors.\n\n"
    "For each method, provide:\n"
    '- "name": The method name\n'
    '- "description": A detailed description of the method\n'
    '- "key_components": List of key components or modules\n'
    '- "inputs": What does this method take as input\n'
    '- "outputs": What does this method produce\n'
    '- "differences_from_prior": How does this differ from previous/existing methods\n\n'
    "Rules:\n"
    "- Include both the main proposed method AND significant sub-methods\n"
    "- Be precise about inputs/outputs\n"
    "- Focus on the NOVEL aspects that distinguish from prior work\n\n"
    'Output a JSON object with a single key "methods" containing an array:\n'
    "```json\n"
    "{\n"
    '  "methods": [\n'
    "    {\n"
    '      "name": "...",\n'
    '      "description": "...",\n'
    '      "key_components": [],\n'
    '      "inputs": [],\n'
    '      "outputs": [],\n'
    '      "differences_from_prior": []\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "Paper content:\n---\n{content}\n---"
)

SCENARIO_SYSTEM_PROMPT = (
    "You are an expert research assistant specializing in identifying "
    "application scenarios and domains in academic papers. "
    "You extract structured information about where and how the research can be applied."
)

SCENARIO_USER_PROMPT = (
    "Analyze the following paper content and extract ALL application scenarios "
    "and domains this paper addresses or could be applied to.\n\n"
    "For each scenario, provide:\n"
    '- "large_scenario": The broad research area '
    '(e.g., "Computer Vision", "Natural Language Processing")\n'
    '- "small_scenario": The specific task or sub-area '
    '(e.g., "Image Segmentation", "Sentiment Analysis")\n'
    '- "extendable_scenarios": Other areas where this approach could potentially be applied\n'
    '- "data_type": What type of data does this scenario involve '
    '(e.g., "images", "text", "video", "audio", "tabular", "multi-modal")\n'
    '- "task_type": The ML task type '
    '(e.g., "classification", "generation", "detection", "segmentation", '
    '"regression", "clustering", "translation")\n\n'
    "Rules:\n"
    "- Extract both explicitly mentioned AND reasonably inferred scenarios\n"
    "- Include the main scenario the paper targets AND potential extensions\n\n"
    'Output a JSON object with a single key "scenarios" containing an array:\n'
    "```json\n"
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "large_scenario": "...",\n'
    '      "small_scenario": "...",\n'
    '      "extendable_scenarios": [],\n'
    '      "data_type": "...",\n'
    '      "task_type": "..."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "Paper content:\n---\n{content}\n---"
)

TECHNIQUE_SYSTEM_PROMPT = (
    "You are an expert research assistant specializing in identifying "
    "technical components and mechanisms in academic papers. "
    "You extract structured information about techniques used."
)

TECHNIQUE_USER_PROMPT = (
    "Analyze the following paper content and extract ALL key technical components, "
    "mechanisms, or techniques that are central to the paper's approach.\n\n"
    "For each technique, provide:\n"
    '- "name": The name of the technique/component '
    '(e.g., "Layer Normalization", "Multi-Head Cross Attention")\n'
    '- "category": The category it belongs to '
    '(e.g., "normalization", "attention mechanism", "loss function", '
    '"data augmentation", "optimization", "feature extraction")\n'
    '- "description": A brief description of what this technique does and how it is used '
    "in this paper\n"
    '- "formula": If a mathematical formula is associated with this technique, include it '
    "in LaTeX format. Otherwise null.\n\n"
    "Rules:\n"
    "- Include both novel techniques proposed AND noteworthy existing techniques used "
    "in a novel way\n"
    "- Be specific about how the technique is applied in THIS paper\n"
    "- Include formulas when they are central to understanding the technique\n\n"
    'Output a JSON object with a single key "techniques" containing an array:\n'
    "```json\n"
    "{\n"
    '  "techniques": [\n'
    "    {\n"
    '      "name": "...",\n'
    '      "category": "...",\n'
    '      "description": "...",\n'
    '      "formula": null\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "Paper content:\n---\n{content}\n---"
)


def get_innovation_prompts() -> tuple:
    return INNOVATION_SYSTEM_PROMPT, INNOVATION_USER_PROMPT


def get_method_prompts() -> tuple:
    return METHOD_SYSTEM_PROMPT, METHOD_USER_PROMPT


def get_scenario_prompts() -> tuple:
    return SCENARIO_SYSTEM_PROMPT, SCENARIO_USER_PROMPT


def get_technique_prompts() -> tuple:
    return TECHNIQUE_SYSTEM_PROMPT, TECHNIQUE_USER_PROMPT
