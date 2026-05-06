"""
Module Registration.

Registers all available modules with their specs and factory functions.
"""

from typing import Any, Dict

from ..registry import ModuleRegistry, ModuleSpec


def _lazy_import(module_path: str, class_name: str, config: Dict[str, Any]):
    import importlib
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name, None)
        if cls:
            return cls(config)
    except (ImportError, AttributeError):
        pass
    return _create_placeholder(config)


def _create_placeholder(config: Dict[str, Any]):
    from ..adapters.base import BaseModule

    class PlaceholderModule(BaseModule):
        def __init__(self, cfg=None):
            self.config = cfg or {}

        async def execute(self, inputs):
            return {
                "placeholder": True,
                "message": "Module not implemented",
                "inputs_received": inputs,
            }

    return PlaceholderModule(config)


_ADAPTERS = {
    "iclr_crawler": ("src.orchestrator.adapters.iclr_crawler", "ICLRCrawlerModule"),
    "idea_extractor": ("src.orchestrator.adapters.idea_extractor", "IdeaExtractorModule"),
    "paper_store": ("src.orchestrator.adapters.paper_store", "PaperStoreModule"),
    "idea_generator": ("src.orchestrator.adapters.idea_generator", "IdeaGeneratorModule"),
    "idea_evaluator": ("src.orchestrator.adapters.idea_evaluator", "IdeaEvaluatorModule"),
    "idea_deduplicator": ("src.orchestrator.adapters.idea_deduplicator", "IdeaDeduplicatorModule"),
    "topk_filter": ("src.orchestrator.adapters.topk_filter", "TopKFilterModule"),
    "idea_reviewer": ("src.orchestrator.adapters.idea_reviewer", "IdeaReviewerModule"),
    "result_exporter": ("src.orchestrator.adapters.result_exporter", "ResultExporterModule"),
    "reader_agent": ("src.orchestrator.adapters.reader_agent", "ReaderAgentModule"),
    "analyst_agent": ("src.orchestrator.adapters.analyst_agent", "AnalystAgentModule"),
    "connector_agent": ("src.orchestrator.adapters.connector_agent", "ConnectorAgentModule"),
    "contrarian_agent": ("src.orchestrator.adapters.contrarian_agent", "ContrarianAgentModule"),
    "synthesizer_agent": ("src.orchestrator.adapters.synthesizer_agent", "SynthesizerAgentModule"),
    "critic_agent": ("src.orchestrator.adapters.critic_agent", "CriticAgentModule"),
    "kb_load": ("src.orchestrator.adapters.kb_load", "KBLoadModule"),
    "kb_save": ("src.orchestrator.adapters.kb_save", "KBSaveModule"),
    "experiment_runner": ("src.orchestrator.adapters.experiment_runner", "ExperimentRunnerModule"),
    "experiment_evaluator": ("src.orchestrator.adapters.experiment_evaluator", "ExperimentEvaluatorModule"),
    "surveyor_agent": ("src.orchestrator.adapters.surveyor_agent", "SurveyorAgentModule"),
    "idea_scout": ("src.orchestrator.adapters.idea_scout", "IdeaScoutModule"),
    "idea_refiner": ("src.orchestrator.adapters.idea_refiner", "IdeaRefinerModule"),
    "exploration_merge": ("src.orchestrator.adapters.exploration_merge", "ExplorationMergeModule"),
    "arxiv_crawler": ("src.orchestrator.adapters.arxiv_crawler", "ArxivCrawlerModule"),
    "arxiv_pdf_pipeline": ("src.orchestrator.adapters.arxiv_pdf_pipeline", "ArxivPDFPipelineModule"),
    "idea_scheduler": ("src.orchestrator.adapters.idea_scheduler", "IdeaSchedulerModule"),
    "replication_agent": ("src.orchestrator.adapters.replication_agent", "ReplicationAgentModule"),
    "transfer_agent": ("src.orchestrator.adapters.transfer_agent", "TransferAgentModule"),
    "critique_agent": ("src.orchestrator.adapters.critique_agent", "CritiqueAgentModule"),
    "theory_agent": ("src.orchestrator.adapters.theory_agent", "TheoryAgentModule"),
    "meta_analysis_agent": ("src.orchestrator.adapters.meta_analysis_agent", "MetaAnalysisAgentModule"),
    "follow_up_agent": ("src.orchestrator.adapters.follow_up_agent", "FollowUpAgentModule"),
    "adversarial_agent": ("src.orchestrator.adapters.adversarial_agent", "AdversarialAgentModule"),
    "limitation_agent": ("src.orchestrator.adapters.limitation_agent", "LimitationAgentModule"),
    "hypothesis_agent": ("src.orchestrator.adapters.hypothesis_agent", "HypothesisAgentModule"),
    "evidence_agent": ("src.orchestrator.adapters.evidence_agent", "EvidenceAgentModule"),
    "paper_code_analyzer": ("src.orchestrator.adapters.paper_code_analyzer", "PaperCodeAnalyzerModule"),
    "paper_code_retrieval": ("src.orchestrator.adapters.paper_code_retrieval", "PaperCodeRetrievalModule"),
    "ablation_analyzer": ("src.orchestrator.adapters.ablation_analyzer", "AblationAnalyzerModule"),
    "keyword_expander": ("src.orchestrator.adapters.keyword_expander", "KeywordExpanderModule"),
    "search_crawler": ("src.orchestrator.adapters.search_crawler", "SearchCrawlerModule"),
    "direction_filter": ("src.orchestrator.adapters.direction_filter", "DirectionFilterModule"),
    "paper_writer": ("src.orchestrator.adapters.paper_writer", "PaperWriterModule"),
    "paper_reviewer": ("src.orchestrator.adapters.paper_reviewer", "PaperReviewerModule"),
    "paper_editor": ("src.orchestrator.adapters.paper_editor", "PaperEditorModule"),
    "external_data": ("src.orchestrator.adapters.external_data", "ExternalDataModule"),
    "threshold_iteration_controller": ("src.orchestrator.adapters.iteration_controllers", "ThresholdIterationControllerModule"),
    "patience_iteration_controller": ("src.orchestrator.adapters.iteration_controllers", "PatienceIterationControllerModule"),
    "improving_iteration_controller": ("src.orchestrator.adapters.iteration_controllers", "ImprovingIterationControllerModule"),
    "llm_iteration_controller": ("src.orchestrator.adapters.iteration_controllers", "LLMIterationControllerModule"),
    "multi_criteria_iteration_controller": ("src.orchestrator.adapters.iteration_controllers", "MultiCriteriaIterationControllerModule"),
    "result_aggregator": ("src.orchestrator.adapters.iteration_controllers", "ResultAggregatorModule"),
    "quality_scorer": ("src.orchestrator.adapters.iteration_controllers", "QualityScorerModule"),
    "paper_retriever": ("src.orchestrator.adapters.paper_retriever", "PaperRetrieverModule"),
    "idea_judge": ("src.orchestrator.adapters.idea_judge", "IdeaJudgeModule"),
    "idea_saver": ("src.orchestrator.adapters.idea_saver", "IdeaSaverModule"),
    "idea_counter": ("src.orchestrator.adapters.idea_counter", "IdeaCounterModule"),
    "llm_keyword_provider": ("src.orchestrator.adapters.crawler_adapters", "LLMKeywordProviderModule"),
    "manual_keyword_provider": ("src.orchestrator.adapters.crawler_adapters", "ManualKeywordProviderModule"),
    "taxonomy_expander": ("src.orchestrator.adapters.crawler_adapters", "TaxonomyExpanderModule"),
    "trend_keyword_provider": ("src.orchestrator.adapters.crawler_adapters", "TrendKeywordProviderModule"),
    "keyword_selector": ("src.orchestrator.adapters.crawler_adapters", "KeywordSelectorModule"),
    "arxiv_summary": ("src.orchestrator.adapters.crawler_adapters", "ArxivSummaryModule"),
    "ncbi_summary": ("src.orchestrator.adapters.crawler_adapters", "NCBISummaryModule"),
    "biorxiv_summary": ("src.orchestrator.adapters.crawler_adapters", "BioRxivSummaryModule"),
    "s2_summary": ("src.orchestrator.adapters.crawler_adapters", "S2SummaryModule"),
    "openreview_summary": ("src.orchestrator.adapters.crawler_adapters", "OpenReviewSummaryModule"),
    "crawl_orchestrator": ("src.orchestrator.adapters.crawler_adapters", "CrawlOrchestratorModule"),
    "crossref_summary": ("src.orchestrator.adapters.crawler_adapters", "CrossRefSummaryModule"),
    "openalex_summary": ("src.orchestrator.adapters.crawler_adapters", "OpenAlexSummaryModule"),
    "dblp_summary": ("src.orchestrator.adapters.crawler_adapters", "DBLPSummaryModule"),
    "plos_summary": ("src.orchestrator.adapters.crawler_adapters", "PLOSSummaryModule"),
    "europe_pmc_summary": ("src.orchestrator.adapters.crawler_adapters", "EuropePMCSummaryModule"),
    "acl_summary": ("src.orchestrator.adapters.crawler_adapters", "ACLSummaryModule"),
    "cvf_summary": ("src.orchestrator.adapters.crawler_adapters", "CVFSummaryModule"),
    "ieee_summary": ("src.orchestrator.adapters.crawler_adapters", "IEEESummaryModule"),
    "frontiers_summary": ("src.orchestrator.adapters.crawler_adapters", "FrontiersSummaryModule"),
    "ssrn_summary": ("src.orchestrator.adapters.crawler_adapters", "SSRNSummaryModule"),
    "springer_summary": ("src.orchestrator.adapters.crawler_adapters", "SpringerSummaryModule"),
    "acs_summary": ("src.orchestrator.adapters.crawler_adapters", "ACSSummaryModule"),
    "pdf_download": ("src.orchestrator.adapters.crawler_adapters", "GenericPDFDownloadModule"),
    "summary_persist": ("src.orchestrator.adapters.crawler_persistence", "SummaryPersistModule"),
    "pdf_download_persist": ("src.orchestrator.adapters.crawler_persistence", "PDFDownloadPersistModule"),
    "paper_search_persist": ("src.orchestrator.adapters.paper_search_persist", "PaperSearchPersistModule"),
    "idea_persist": ("src.orchestrator.adapters.idea_persist", "IdeaPersistModule"),
    "pdf_kit_parse": ("src.orchestrator.adapters.pdf_kit_parse", "PDFKitParseModule"),
    "pdf_kit_parse_batch": ("src.orchestrator.adapters.pdf_kit_parse_batch", "PDFKitParseBatchModule"),
    "pdf_kit_parse_persist": ("src.orchestrator.adapters.pdf_kit_parse_persist", "PDFKitParsePersistModule"),
    "pek_start": ("src.orchestrator.adapters.pek_start", "PEKStartModule"),
    "pek_parse": ("src.orchestrator.adapters.pek_parse", "PEKParseModule"),
    "pek_stop": ("src.orchestrator.adapters.pek_stop", "PEKStopModule"),
    "parsed_folder_feeder": ("src.orchestrator.adapters.parsed_folder_feeder", "ParsedFolderFeederModule"),
    "parsed_folder_freshness_feeder": ("src.orchestrator.adapters.parsed_folder_freshness_feeder", "ParsedFolderFreshnessFeederModule"),
    "parsed_folder_loader": ("src.orchestrator.adapters.parsed_folder_loader", "ParsedFolderLoaderModule"),
    "title_persist": ("src.orchestrator.adapters.title_persist", "TitlePersistModule"),
    "title_loader": ("src.orchestrator.adapters.title_loader", "TitleLoaderModule"),
    "paper_id_allocator": ("src.orchestrator.adapters.paper_id_allocator", "PaperIDAllocatorModule"),
    "pdf_mover": ("src.orchestrator.adapters.pdf_mover", "PDFMoverModule"),
    "experiment_plan_generator": ("src.orchestrator.adapters.experiment_plan_generator", "ExperimentPlanGeneratorModule"),
    "experiment_plan_evaluator": ("src.orchestrator.adapters.experiment_plan_evaluator", "ExperimentPlanEvaluatorModule"),
    "experiment_plan_reviser": ("src.orchestrator.adapters.experiment_plan_reviser", "ExperimentPlanReviserModule"),
    "experiment_resource_checker": ("src.orchestrator.adapters.experiment_resource_checker", "ExperimentResourceCheckerModule"),
    "experiment_executor_opencode": ("src.orchestrator.adapters.experiment_executor_opencode", "ExperimentExecutorOpencodeModule"),
    "experiment_runner_cli": ("src.orchestrator.adapters.experiment_runner_cli", "ExperimentRunnerCliModule"),
    "experiment_verifier_cli": ("src.orchestrator.adapters.experiment_verifier_cli", "ExperimentVerifierCliModule"),
    "paper_cli_runner": ("src.orchestrator.adapters.paper_cli_runner", "PaperCliRunnerModule"),
    "experiment_goal_evaluator": ("src.orchestrator.adapters.experiment_goal_evaluator", "ExperimentGoalEvaluatorModule"),
    "experiment_report_generator": ("src.orchestrator.adapters.experiment_report_generator", "ExperimentReportGeneratorModule"),
    "chart_code_generator": ("src.orchestrator.adapters.chart_code_generator", "ChartCodeGeneratorModule"),
    "experiment_persist": ("src.orchestrator.adapters.experiment_persist", "ExperimentPersistModule"),
    "image_prompt_generator": ("src.orchestrator.adapters.image_prompt_generator", "ImagePromptGeneratorModule"),
    "image_generator": ("src.orchestrator.adapters.image_generator", "ImageGeneratorModule"),
    "image_persist": ("src.orchestrator.adapters.image_persist", "ImagePersistModule"),
    "paper_outline_generator": ("src.orchestrator.adapters.paper_outline_generator", "PaperOutlineGeneratorModule"),
    "paper_section_writer": ("src.orchestrator.adapters.paper_section_writer", "PaperSectionWriterModule"),
    "paper_coherence_checker": ("src.orchestrator.adapters.paper_coherence_checker", "PaperCoherenceCheckerModule"),
    "paper_formatter": ("src.orchestrator.adapters.paper_formatter", "PaperFormatterModule"),
    "paper_persist": ("src.orchestrator.adapters.paper_persist", "PaperPersistModule"),
    "reference_collector": ("src.orchestrator.adapters.reference_collector", "ReferenceCollectorModule"),
    "reference_gap_analyzer": ("src.orchestrator.adapters.reference_gap_analyzer", "ReferenceGapAnalyzerModule"),
    "bibtex_generator": ("src.orchestrator.adapters.bibtex_generator", "BibtexGeneratorModule"),
    "citation_inserter": ("src.orchestrator.adapters.citation_inserter", "CitationInserterModule"),
    "reference_integrity_checker": ("src.orchestrator.adapters.reference_integrity_checker", "ReferenceIntegrityCheckerModule"),
    "paper_summary_search": ("src.orchestrator.adapters.paper_summary_search", "PaperSummarySearchModule"),
    "pdf_queue_feeder": ("src.orchestrator.adapters.pdf_queue_feeder", "PDFQueueFeederModule"),
    "parse_result_gate": ("src.orchestrator.adapters.parse_result_gate", "ParseResultGateModule"),
    "title_result_gate": ("src.orchestrator.adapters.title_result_gate", "TitleResultGateModule"),
    "summary_result_gate": ("src.orchestrator.adapters.summary_result_gate", "SummaryResultGateModule"),
    "id_align_gate": ("src.orchestrator.adapters.id_align_gate", "IDAlignGateModule"),
    "pdf_parser": ("src.orchestrator.adapters.pdf_parser", "PDFParserModule"),
    "pdf_extraction": ("src.orchestrator.adapters.pdf_parser", "PDFExtractionModule"),
    "title_extractor": ("src.orchestrator.adapters.title_extractor", "TitleExtractorModule"),
    "paper_summary_agent": ("src.orchestrator.adapters.paper_summary_agent", "PaperSummaryAgentModule"),
    "summary_accumulator": ("src.orchestrator.adapters.summary_accumulator", "SummaryAccumulatorModule"),
    "idea_evolution_agent": ("src.orchestrator.adapters.idea_evolution_agent", "IdeaEvolutionAgentModule"),
    "round_controller": ("src.orchestrator.adapters.round_controller", "RoundControllerModule"),
    "best_idea_selector": ("src.orchestrator.adapters.best_idea_selector", "BestIdeaSelectorModule"),
    "paper_md_assembler": ("src.orchestrator.adapters.paper_md_assembler", "PaperMdAssemblerModule"),
    "experiment_success_gate": ("src.orchestrator.adapters.experiment_success_gate", "ExperimentSuccessGateModule"),
    "incremental_persistence": ("src.orchestrator.adapters.incremental_persistence", "IncrementalPersistenceModule"),
    "kg_extract": ("src.orchestrator.adapters.kg_extract", "KGExtractModule"),
    "kg_dedup": ("src.orchestrator.adapters.kg_dedup", "KGDedupModule"),
    "kg_embed": ("src.orchestrator.adapters.kg_embed", "KGEmbedModule"),
    "kg_write_node": ("src.orchestrator.adapters.kg_write_node", "KGWriteNodeModule"),
    "kg_build_internal_edge": ("src.orchestrator.adapters.kg_build_internal_edge", "KGBuildInternalEdgeModule"),
    "kg_build_struct_edge": ("src.orchestrator.adapters.kg_build_struct_edge", "KGBuildStructEdgeModule"),
    "kg_build_semantic_edge": ("src.orchestrator.adapters.kg_build_semantic_edge", "KGBuildSemanticEdgeModule"),
    "kg_random_walk": ("src.orchestrator.adapters.kg_random_walk", "KGRandomWalkModule"),
    "kg_retrospect": ("src.orchestrator.adapters.kg_retrospect", "KGRetrospectModule"),
    "kg_vector_search": ("src.orchestrator.adapters.kg_vector_search", "KGVectorSearchModule"),
    "kg_graph_traverse": ("src.orchestrator.adapters.kg_graph_traverse", "KGGraphTraverseModule"),
    "kg_nl_query": ("src.orchestrator.adapters.kg_nl_query", "KGNLQueryModule"),
    "kg_abstract_enrich": ("src.orchestrator.adapters.kg_abstract_enrich", "KGAbstractEnrichModule"),
    "kg_synthesize": ("src.orchestrator.adapters.kg_synthesize", "KGSynthesizeModule"),
    "kg_crud": ("src.orchestrator.adapters.kg_crud", "KGCRUDModule"),
    "kg_rebuild": ("src.orchestrator.adapters.kg_rebuild", "KGRebuildModule"),
    "kg_prune": ("src.orchestrator.adapters.kg_prune", "KGPruneModule"),
    "paper_db_reader": ("src.orchestrator.adapters.paper_db_reader", "PaperDBReaderModule"),
    "paper_intra_index": ("src.orchestrator.adapters.paper_intra_index", "PaperIntraIndexModule"),
    "paper_intra_index_incremental": ("src.orchestrator.adapters.paper_intra_index_incremental", "PaperIntraIndexIncrementalModule"),
    "kg_cross_paper_discover": ("src.orchestrator.adapters.kg_cross_paper_discover", "KGCrossPaperDiscoverModule"),
}


def _make_factory(module_path: str, class_name: str):
    def factory(config: Dict[str, Any]):
        return _lazy_import(module_path, class_name, config)
    return factory


def get_all_module_specs():
    specs = []

    specs.append(ModuleSpec(
        name="iclr_crawler",
        display_name="ICLR Crawler",
        description="Crawl ICLR papers from OpenReview API",
        input_schema={
            "years": "List[int]",
            "min_rating": "float",
            "accepted_only": "bool",
            "max_papers_per_year": "int",
            "output_dir": "str",
            "max_concurrent": "int",
            "download_pdf": "bool",
        },
        output_schema={"pdf_dir": "str", "metadata": "List[Dict]", "paper_count": "int"},
        tags={"crawler", "iclr"},
        factory=_make_factory(*_ADAPTERS["iclr_crawler"]),
    ))

    specs.append(ModuleSpec(
        name="idea_extractor",
        display_name="Idea Extractor",
        description="Extract innovations, methods, scenarios, techniques from papers",
        input_schema={"papers": "List[Dict]"},
        output_schema={
            "all_innovations": "List[Dict]",
            "all_methods": "List[Dict]",
            "all_scenarios": "List[Dict]",
            "all_techniques": "List[Dict]",
        },
        tags={"core", "llm_required"},
        factory=_make_factory(*_ADAPTERS["idea_extractor"]),
    ))

    specs.append(ModuleSpec(
        name="paper_store",
        display_name="Paper Store",
        description="Store papers in VectorDB for retrieval",
        input_schema={"papers": "List[Dict]", "innovations": "List[Dict]"},
        output_schema={"stored_count": "int", "collection_name": "str"},
        tags={"vector_db"},
        factory=_make_factory(*_ADAPTERS["paper_store"]),
    ))

    specs.append(ModuleSpec(
        name="idea_generator",
        display_name="Idea Generator",
        description="Generate research ideas from innovations and references",
        input_schema={
            "innovations": "List[Dict]",
            "references": "List[Dict]",
            "task_domain": "str",
            "target_count": "int",
            "existing_ideas": "List[Dict]",
            "focus_areas": "List[str]",
        },
        output_schema={"ideas": "List[Idea]", "report": "str", "count": "int", "avg_score": "float"},
        tags={"core", "llm_required"},
        factory=_make_factory(*_ADAPTERS["idea_generator"]),
    ))

    specs.append(ModuleSpec(
        name="idea_evaluator",
        display_name="Idea Evaluator",
        description="Evaluate ideas on novelty, feasibility, and impact",
        input_schema={"ideas": "List[Idea]", "available_datasets": "List[str]", "available_compute": "str"},
        output_schema={"evaluations": "List[Evaluation]", "ranked_ideas": "List[Idea]", "summary": "str", "avg_score": "float"},
        tags={"core", "llm_required"},
        factory=_make_factory(*_ADAPTERS["idea_evaluator"]),
    ))

    specs.append(ModuleSpec(
        name="idea_deduplicator",
        display_name="Idea Deduplicator",
        description="Deduplicate ideas using embedding similarity",
        input_schema={"ideas": "List[Dict]", "existing_ideas": "List[Dict]"},
        output_schema={"unique_ideas": "List[Dict]", "duplicate_count": "int"},
        tags={"dedup"},
        factory=_make_factory(*_ADAPTERS["idea_deduplicator"]),
    ))

    specs.append(ModuleSpec(
        name="topk_filter",
        display_name="Top-K Filter",
        description="Filter top-K ideas by score",
        input_schema={"ranked_ideas": "List[Dict]", "target_count": "int", "min_score": "float"},
        output_schema={"selected_ideas": "List[Dict]", "rejected_count": "int"},
        tags={"filter"},
        factory=_make_factory(*_ADAPTERS["topk_filter"]),
    ))

    specs.append(ModuleSpec(
        name="idea_reviewer",
        display_name="Idea Reviewer",
        description="Detailed structured review of ideas",
        input_schema={"ideas": "List[Dict]"},
        output_schema={"reviewed_ideas": "List[Dict]", "review_report": "str"},
        tags={"review", "llm_required"},
        factory=_make_factory(*_ADAPTERS["idea_reviewer"]),
    ))

    specs.append(ModuleSpec(
        name="result_exporter",
        display_name="Result Exporter",
        description="Export final results to JSON and Markdown",
        input_schema={"ideas": "List[Dict]", "generation_report": "str", "evaluation_report": "str"},
        output_schema={"export_id": "int", "idea_count": "int", "markdown_content": "str"},
        tags={"export"},
        factory=_make_factory(*_ADAPTERS["result_exporter"]),
    ))

    specs.append(ModuleSpec(
        name="ablation_analyzer",
        display_name="Ablation Analyzer",
        description="Analyze method components via ablation study — remove each component and compare metrics",
        input_schema={
            "experiment_design": "Dict",
            "eval_result": "Dict",
            "components": "List[str]",
        },
        output_schema={
            "ablation_results": "List[Dict]",
            "ablation_recommendations": "List[str]",
            "baseline_metrics": "Dict[str,float]",
            "summary": "str",
        },
        tags={"experiment", "ablation"},
        factory=_make_factory(*_ADAPTERS["ablation_analyzer"]),
    ))

    specs.append(ModuleSpec(
        name="keyword_expander",
        display_name="Keyword Expander",
        description="Expand a research direction into structured keywords, search queries, and sub-topics via LLM",
        input_schema={"direction_name": "str", "direction_description": "str"},
        output_schema={
            "keywords": "List[str]",
            "sub_topics": "List[str]",
            "arxiv_categories": "List[str]",
            "semantic_scholar_queries": "List[str]",
            "arxiv_queries": "List[str]",
            "related_terms": "List[str]",
            "research_threads": "List[str]",
            "expanded_direction": "Dict",
        },
        tags={"agent", "llm_required", "direction", "search"},
        factory=_make_factory(*_ADAPTERS["keyword_expander"]),
    ))

    specs.append(ModuleSpec(
        name="search_crawler",
        display_name="Multi-Source Search Crawler",
        description="Search academic papers from Semantic Scholar and arXiv using keyword queries",
        input_schema={
            "semantic_scholar_queries": "List[str]",
            "arxiv_queries": "List[str]",
            "max_papers_per_source": "int",
            "year_from": "int",
            "year_to": "int",
        },
        output_schema={
            "metadata": "List[Dict]",
            "paper_count": "int",
            "source_stats": "Dict",
            "total_found": "int",
            "has_pdfs": "bool",
        },
        tags={"crawler", "search", "semantic_scholar", "arxiv"},
        factory=_make_factory(*_ADAPTERS["search_crawler"]),
    ))

    specs.append(ModuleSpec(
        name="direction_filter",
        display_name="Direction Relevance Filter",
        description="Filter papers by relevance to a research direction using keyword matching and LLM scoring",
        input_schema={
            "papers": "List[Dict]",
            "direction": "Dict",
            "max_papers": "int",
            "relevance_threshold": "float",
        },
        output_schema={
            "filtered_papers": "List[Dict]",
            "relevance_scores": "List[float]",
            "filter_stats": "Dict",
        },
        tags={"filter", "llm_required", "direction"},
        factory=_make_factory(*_ADAPTERS["direction_filter"]),
    ))

    specs.append(ModuleSpec(
        name="paper_writer",
        display_name="Paper Writer",
        description="Generate research paper drafts from ideas and experiment results",
        input_schema={"title": "str", "authors": "List[str]", "idea": "Dict", "experiment_results": "Dict", "references": "List[Dict]"},
        output_schema={"draft": "Dict", "output_path": "str", "draft_id": "int"},
        tags={"writing", "llm_required"},
        factory=_make_factory(*_ADAPTERS["paper_writer"]),
    ))

    specs.append(ModuleSpec(
        name="paper_reviewer",
        display_name="Paper Reviewer",
        description="Review paper drafts with structured critique scoring",
        input_schema={"paper_content": "Dict", "paper_id": "str"},
        output_schema={"overall_score": "float", "summary": "str", "critiques": "List[Dict]", "confidence": "float"},
        tags={"review", "llm_required"},
        factory=_make_factory(*_ADAPTERS["paper_reviewer"]),
    ))

    specs.append(ModuleSpec(
        name="paper_editor",
        display_name="Paper Editor",
        description="Edit paper drafts based on review comments",
        input_schema={"paper_draft": "Dict", "review_comments": "List[Dict]"},
        output_schema={"revised_draft": "Dict", "edits_made": "List[Dict]", "summary": "str"},
        tags={"writing", "llm_required"},
        factory=_make_factory(*_ADAPTERS["paper_editor"]),
    ))

    specs.append(ModuleSpec(
        name="external_data",
        display_name="External Data",
        description="Inject external configuration data into pipeline context",
        input_schema={},
        output_schema={},
        tags={"config"},
        factory=_make_factory(*_ADAPTERS["external_data"]),
    ))

    _AGENT_SPECS = [
        ("reader_agent", "Reader Agent", "Compress papers into structured insights",
         {"papers": "List[Dict]", "existing_paper_ids": "List[str]", "existing_insights": "List[Dict]"},
         {"compressed_insights": "List[Dict]", "new_insight_count": "int", "insight_count": "int"}),
        ("analyst_agent", "Analyst Agent", "Cluster insights and identify gaps",
         {"compressed_insights": "List[Dict]"},
         {"analyst_seeds": "List[Dict]", "clusters": "List[Dict]", "knowledge_base": "Dict", "cross_cluster_gaps": "List[Dict]"}),
        ("connector_agent", "Connector Agent", "Find cross-domain connections",
         {"compressed_insights": "List[Dict]"},
         {"connector_seeds": "List[Dict]", "cross_domain_pairs": "List[Dict]", "knowledge_base": "Dict"}),
        ("contrarian_agent", "Contrarian Agent", "Challenge assumptions for novel ideas",
         {"compressed_insights": "List[Dict]"},
         {"contrarian_seeds": "List[Dict]", "knowledge_base": "Dict"}),
        ("synthesizer_agent", "Synthesizer Agent", "Expand seeds into full proposals",
         {"analyst_seeds": "List[Dict]", "connector_seeds": "List[Dict]", "contrarian_seeds": "List[Dict]", "existing_ideas": "List[Dict]", "compressed_insights": "List[Dict]"},
         {"full_ideas": "List[Dict]", "seed_count": "int", "idea_count": "int"}),
        ("critic_agent", "Critic Agent", "Evaluate and rank ideas",
         {"full_ideas": "List[Dict]", "compressed_insights": "List[Dict]", "existing_ideas": "List[Dict]"},
         {"ranked_ideas": "List[Dict]", "final_count": "int", "avg_score": "float"}),
    ]
    for name, display, desc, in_schema, out_schema in _AGENT_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"agent", "llm_required"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    specs.append(ModuleSpec(
        name="kb_load",
        display_name="Knowledge Base Load",
        description="Load accumulated knowledge base from previous runs",
        input_schema={"store_dir": "str"},
        output_schema={
            "existing_insights": "List[Dict]",
            "existing_ideas": "List[Dict]",
            "existing_analyst_seeds": "List[Dict]",
            "existing_connector_seeds": "List[Dict]",
            "existing_contrarian_seeds": "List[Dict]",
            "existing_paper_ids": "List[str]",
            "total_idea_count": "int",
            "existing_replication_problems": "List[Dict]",
            "existing_transfer_ideas": "List[Dict]",
            "existing_critiques": "List[Dict]",
            "existing_theory_improvements": "List[Dict]",
            "existing_trends": "List[Dict]",
            "existing_meta_gaps": "List[Dict]",
            "existing_follow_up_ideas": "List[Dict]",
            "existing_failure_cases": "List[Dict]",
            "existing_limitation_extensions": "List[Dict]",
            "existing_hypotheses": "List[Dict]",
            "existing_evidence_items": "List[Dict]",
        },
        tags={"knowledge_base"},
        factory=_make_factory(*_ADAPTERS["kb_load"]),
    ))

    specs.append(ModuleSpec(
        name="kb_save",
        display_name="Knowledge Base Save",
        description="Merge new results into accumulated knowledge base",
        input_schema={
            "compressed_insights": "List[Dict]",
            "analyst_seeds": "List[Dict]",
            "connector_seeds": "List[Dict]",
            "contrarian_seeds": "List[Dict]",
            "ranked_ideas": "List[Dict]",
            "replication_problems": "List[Dict]",
            "transfer_ideas": "List[Dict]",
            "critiques": "List[Dict]",
            "theory_improvements": "List[Dict]",
            "trends": "List[Dict]",
            "meta_gaps": "List[Dict]",
            "follow_up_ideas": "List[Dict]",
            "failure_cases": "List[Dict]",
            "limitation_extensions": "List[Dict]",
            "hypotheses": "List[Dict]",
            "evidence_items": "List[Dict]",
        },
        output_schema={
            "total_insights": "int",
            "total_seeds": "int",
            "total_ideas": "int",
            "new_ideas_added": "int",
            "new_replication_problems": "int",
            "new_transfer_ideas": "int",
            "new_critiques": "int",
            "new_theory_improvements": "int",
            "new_trends": "int",
            "new_meta_gaps": "int",
            "new_follow_up_ideas": "int",
            "new_failures": "int",
            "new_limitations": "int",
            "new_hypotheses": "int",
            "new_evidence": "int",
        },
        tags={"knowledge_base"},
        factory=_make_factory(*_ADAPTERS["kb_save"]),
    ))

    specs.append(ModuleSpec(
        name="experiment_runner",
        display_name="Experiment Runner (OpenCode)",
        description="Execute experiments by invoking opencode coding agent in headless mode",
        input_schema={
            "designed_experiments": "List[Dict]",
            "idea_id": "str",
            "idea_title": "str",
            "idea_description": "str",
        },
        output_schema={
            "experiment_results": "List[Dict]",
            "execution_metrics": "Dict[str,float]",
            "best_result": "Dict",
            "summary": "str",
        },
        tags={"experiment", "opencode", "execution"},
        factory=_make_factory(*_ADAPTERS["experiment_runner"]),
    ))

    specs.append(ModuleSpec(
        name="experiment_evaluator",
        display_name="Experiment Evaluator",
        description="Evaluate experiment results using metric computation, baseline comparison, and report generation",
        input_schema={
            "experiment_results": "List[Dict]",
            "evaluation_metrics": "List[str]",
            "task_type": "str",
        },
        output_schema={
            "evaluation_metrics": "Dict[str,float]",
            "evaluation_report": "str",
            "comparison_with_baseline": "Dict",
        },
        tags={"experiment", "evaluation"},
        factory=_make_factory(*_ADAPTERS["experiment_evaluator"]),
    ))

    specs.append(ModuleSpec(
        name="surveyor_agent",
        display_name="Surveyor Agent",
        description="Generate literature survey for a research direction",
        input_schema={"papers": "List[Dict]", "direction": "Dict"},
        output_schema={"literature_survey": "Dict"},
        tags={"agent", "llm_required", "direction"},
        factory=_make_factory(*_ADAPTERS["surveyor_agent"]),
    ))

    specs.append(ModuleSpec(
        name="idea_scout",
        display_name="Idea Scout",
        description="Independently search literature for each idea",
        input_schema={"ideas": "List[Dict]", "direction": "Dict"},
        output_schema={"explorations": "List[Dict]"},
        tags={"agent", "llm_required", "exploration"},
        factory=_make_factory(*_ADAPTERS["idea_scout"]),
    ))

    specs.append(ModuleSpec(
        name="idea_refiner",
        display_name="Idea Refiner",
        description="Refine ideas based on literature exploration results",
        input_schema={"ideas": "List[Dict]", "explorations": "List[Dict]", "direction": "Dict"},
        output_schema={"refined_ideas": "List[Dict]"},
        tags={"agent", "llm_required", "refinement"},
        factory=_make_factory(*_ADAPTERS["idea_refiner"]),
    ))

    specs.append(ModuleSpec(
        name="exploration_merge",
        display_name="Exploration Merge",
        description="Merge per-idea exploration results into knowledge base",
        input_schema={"explorations": "List[Dict]", "refined_ideas": "List[Dict]"},
        output_schema={"saved_explorations": "int", "refined_ideas": "List[Dict]"},
        tags={"knowledge_base", "exploration"},
        factory=_make_factory(*_ADAPTERS["exploration_merge"]),
    ))

    specs.append(ModuleSpec(
        name="arxiv_crawler",
        display_name="arXiv Crawler",
        description="Crawl papers from arXiv API by category (e.g. hep-lat)",
        input_schema={"categories": "List[str]", "max_papers": "int", "download_pdf": "bool"},
        output_schema={"metadata": "List[Dict]", "paper_count": "int", "has_pdfs": "bool"},
        tags={"crawler", "arxiv"},
        factory=_make_factory(*_ADAPTERS["arxiv_crawler"]),
    ))

    specs.append(ModuleSpec(
        name="arxiv_pdf_pipeline",
        display_name="arXiv PDF Pipeline",
        description="Download and extract arXiv PDF content (text, tables, formulas)",
        input_schema={"metadata": "List[Dict]", "download_dir": "str", "extraction_dir": "str"},
        output_schema={"extractions": "List[Dict]", "extraction_count": "int"},
        tags={"pipeline", "pdf", "extraction", "arxiv"},
        factory=_make_factory(*_ADAPTERS["arxiv_pdf_pipeline"]),
    ))

    specs.append(ModuleSpec(
        name="idea_scheduler",
        display_name="Idea Scheduler",
        description="Submit, evaluate, record, and rank ideas with persistent scheduling",
        input_schema={"ranked_ideas": "List[Dict]", "batch_id": "str"},
        output_schema={"scheduled_count": "int", "evaluation_count": "int", "scheduler_stats": "Dict", "all_ideas_count": "int"},
        tags={"scheduler", "evaluation", "persistence"},
        factory=_make_factory(*_ADAPTERS["idea_scheduler"]),
    ))

    _NEW_AGENT_SPECS = [
        ("replication_agent", "Replication Agent", "Analyze papers for reproducibility issues",
         {"papers": "List[Dict]"}, {"replication_problems": "List[Dict]", "problem_count": "int"}),
        ("transfer_agent", "Transfer Agent", "Identify cross-domain method transfers",
         {"compressed_insights": "List[Dict]", "source_domain": "str", "target_domain": "str"},
         {"transfer_ideas": "List[Dict]", "transfer_count": "int"}),
        ("critique_agent", "Critique Agent", "Deep flaw analysis of individual papers",
         {"papers": "List[Dict]"}, {"critiques": "List[Dict]", "critique_count": "int"}),
        ("theory_agent", "Theory Agent", "Analyze theoretical foundations for improvements",
         {"papers": "List[Dict]"}, {"theory_improvements": "List[Dict]", "improvement_count": "int"}),
        ("meta_analysis_agent", "Meta Analysis Agent", "Discover trends and gaps across many papers",
         {"compressed_insights": "List[Dict]"},
         {"trends": "List[Dict]", "meta_gaps": "List[Dict]", "trend_count": "int", "gap_count": "int"}),
        ("follow_up_agent", "Follow-Up Agent", "Track hot papers and generate follow-up ideas",
         {"papers": "List[Dict]"}, {"follow_up_ideas": "List[Dict]", "follow_up_count": "int"}),
        ("adversarial_agent", "Adversarial Agent", "Find failure cases in papers' methods",
         {"papers": "List[Dict]"}, {"failure_cases": "List[Dict]", "failure_case_count": "int"}),
        ("limitation_agent", "Limitation Agent", "Turn stated limitations into research extensions",
         {"papers": "List[Dict]"}, {"limitation_extensions": "List[Dict]", "extension_count": "int"}),
        ("hypothesis_agent", "Hypothesis Agent", "Generate testable hypotheses from insights",
         {"compressed_insights": "List[Dict]", "context": "str"},
         {"hypotheses": "List[Dict]", "hypothesis_count": "int"}),
        ("evidence_agent", "Evidence Agent", "Collect supporting/refuting evidence for hypotheses",
         {"hypotheses": "List[Dict]", "compressed_insights": "List[Dict]"},
         {"evidence_items": "List[Dict]", "evidence_count": "int"}),
        ("paper_code_analyzer", "Paper-Code Analyzer", "Analyze paper-code mappings and extract implementation patterns",
         {"paper_id": "str", "repo_id": "str", "repo_path": "str", "paper_title": "str", "paper_innovations": "List[str]", "paper_md_path": "str"},
         {"analysis_id": "str", "mapping_count": "int", "pattern_count": "int", "tech_stack": "List[str]"}),
        ("paper_code_retrieval", "Paper-Code Retrieval", "Retrieve similar implementations for a given idea or query",
         {"query": "str", "top_k": "int", "filters": "Dict", "generate_guide": "bool"},
         {"results": "List[Dict]", "result_count": "int", "implementation_guide": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _NEW_AGENT_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"agent", "llm_required"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _LOOP_AGENT_SPECS = [
        ("paper_retriever", "Paper Retriever", "Randomly retrieve N parsed papers from papers.db",
         {"num_papers": "int"},
         {"papers": "List[Dict]", "paper_count": "int", "innovations": "List[Dict]", "references": "List[Dict]"}),
        ("idea_judge", "Idea Judge", "Score-based gate: accept idea if score >= threshold, otherwise reject",
         {"idea": "Dict", "overall_score": "float"},
         {"_route": "str", "idea": "Dict", "overall_score": "float", "judge_decision": "str"}),
        ("idea_saver", "Idea Saver", "Save accepted idea to local file named by timestamp",
         {"idea": "Dict", "overall_score": "float"},
         {"save_success": "bool", "saved_path": "str", "idea_title": "str"}),
        ("idea_counter", "Idea Counter", "Count accepted ideas and control iteration loop until target count reached",
         {"save_success": "bool", "judge_decision": "str"},
         {"_route": "str", "accepted_count": "int", "target_count": "int", "total_iterations": "int"}),
    ]
    for name, display, desc, in_schema, out_schema in _LOOP_AGENT_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"agent", "loop_control"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _CRAWLER_MODULE_SPECS = [
        ("llm_keyword_provider", "LLM Keyword Provider", "Generate academic search keywords from content using LLM",
         {"content": "str", "domain": "str", "max_keywords": "int"},
         {"keywords": "List[Dict]", "keyword_count": "int"}),
        ("manual_keyword_provider", "Manual Keyword Provider", "Use a pre-defined list of keywords",
         {"keywords": "List[str]", "domain": "str"},
         {"keywords": "List[Dict]", "keyword_count": "int"}),
        ("taxonomy_expander", "Taxonomy Expander", "Expand a domain/category into academic search keywords",
         {"domain": "str", "category": "str", "max_keywords": "int"},
         {"keywords": "List[Dict]", "keyword_count": "int"}),
        ("trend_keyword_provider", "Trend Keyword Provider", "Extract trending keywords from recent publications",
         {"domain": "str", "days": "int", "max_keywords": "int"},
         {"keywords": "List[Dict]", "keyword_count": "int"}),
        ("keyword_selector", "Keyword Selector", "Select one keyword from a list using a strategy (sequential/random/confidence)",
         {"keywords": "List[Dict]", "strategy": "str"},
         {"keyword": "Dict", "selected_keyword": "str", "keyword_count": "int"}),
        ("arxiv_summary", "arXiv Summary Agent", "Search and fetch paper metadata from arXiv API",
         {"keywords": "List[str]", "categories": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("ncbi_summary", "NCBI Summary Agent", "Search PubMed and fetch paper metadata via NCBI E-utilities",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("biorxiv_summary", "bioRxiv Summary Agent", "Search bioRxiv/medRxiv for preprint paper metadata",
         {"keywords": "List[str]", "domain": "str", "server": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("s2_summary", "Semantic Scholar Summary Agent", "Search Semantic Scholar for paper metadata across all domains",
         {"keywords": "List[str]", "domain": "str", "venue": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("openreview_summary", "OpenReview Summary Agent", "Search OpenReview for conference paper metadata (ICLR/NeurIPS/ICML)",
         {"keywords": "List[str]", "venue": "str", "year_from": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("crawl_orchestrator", "Crawl Orchestrator", "Coordinate multi-platform paper search with PDF download",
         {"keywords": "List[str]", "domain": "str", "venue": "str", "year_from": "int", "year_to": "int", "max_papers": "int", "download_pdf": "bool"},
         {"domain": "str", "total": "int", "downloaded": "int", "paywalled": "int", "papers": "List[Dict]", "pdf_results": "List[Dict]"}),
        ("crossref_summary", "CrossRef Summary Agent", "Search CrossRef for scholarly publication metadata",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("openalex_summary", "OpenAlex Summary Agent", "Search OpenAlex for open scholarly metadata across all domains",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("dblp_summary", "DBLP Summary Agent", "Search DBLP for computer science bibliography metadata",
         {"keywords": "List[str]", "domain": "str", "venue": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("plos_summary", "PLOS Summary Agent", "Search PLOS journals for open-access life science publications",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("europe_pmc_summary", "Europe PMC Summary Agent", "Search Europe PMC for biomedical and life science literature",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("acl_summary", "ACL Summary Agent", "Search ACL Anthology for computational linguistics publications",
         {"keywords": "List[str]", "domain": "str", "venue": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("cvf_summary", "CVF Summary Agent", "Search CVF for computer vision conference papers (CVPR/ICCV/ECCV)",
         {"keywords": "List[str]", "domain": "str", "venue": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("ieee_summary", "IEEE Summary Agent", "Search IEEE Xplore for engineering and technology publications",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("frontiers_summary", "Frontiers Summary Agent", "Search Frontiers journals for open-access research articles",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("ssrn_summary", "SSRN Summary Agent", "Search SSRN for social science and economics preprints",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("springer_summary", "Springer Summary Agent", "Search Springer Nature for scientific and technical publications",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("acs_summary", "ACS Summary Agent", "Search ACS publications for chemistry research articles",
         {"keywords": "List[str]", "domain": "str", "year_from": "int", "year_to": "int", "max_papers": "int"},
         {"metadata": "List[Dict]", "paper_count": "int", "source": "str"}),
        ("pdf_download", "PDF Download", "Download PDFs for papers using the multi-agent download pipeline",
         {"papers": "List[Dict]", "metadata": "List[Dict]", "output_dir": "str"},
         {"results": "List[Dict]", "downloaded": "int", "failed": "int"}),
    ]
    for name, display, desc, in_schema, out_schema in _CRAWLER_MODULE_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"crawler", "multi_domain"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _PERSIST_MODULE_SPECS = [
        ("summary_persist", "Summary Persist", "Persist paper metadata (including pdf_path) from summary agents into papers.db",
         {"metadata": "List[Dict]", "source": "str", "domain": "str"},
         {"metadata": "List[Dict]", "paper_count": "int", "new_count": "int", "updated_count": "int", "persisted_ids": "List[str]"}),
        ("pdf_download_persist", "PDF Download Persist", "Persist PDF download results (file_size, file_hash, etc.) into pdf_downloads table",
         {"results": "List[Dict]", "metadata": "List[Dict]", "source": "str"},
         {"results": "List[Dict]", "downloaded": "int", "failed": "int", "persisted_download_ids": "List[str]"}),
        ("pdf_kit_parse_persist", "PDF Kit Parse Persist", "Persist PDF structured extraction results (sections, tables, images, formulas) into papers.db",
         {"parsed_papers": "List[Dict]", "engine": "str", "figures_base_dir": "str"},
         {"persisted_count": "int", "skipped_count": "int", "db_path": "str", "figures_dir": "str"}),
        ("idea_persist", "Idea Persist", "Persist idea with source into knowledge_store.db raw_ideas table",
         {"idea": "str|Dict", "source": "str", "source_type": "str", "extra": "Dict"},
         {"save_success": "bool", "idea_id": "int", "source": "str", "source_type": "str"}),
        ("paper_search_persist", "Paper Search Persist",
         "Folder-only persistence for paper-search results: writes summaries/<id>.json (full raw API response), references/<id>.json (S2 references), pdfs/<id>.pdf, and index_<tag>.jsonl. No DB writes.",
         {"metadata": "List[Dict]", "pdf_results": "List[Dict]", "source": "str"},
         {"persisted_count": "int", "pdf_count": "int", "references_count": "int", "index_path": "str", "output_dir": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _PERSIST_MODULE_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"persistence", "crawler"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    specs.append(ModuleSpec(
        name="pdf_kit_parse",
        display_name="PDF-Extract-Kit Parser",
        description="Parse PDF files into structured content (text, formulas, tables, figures) using PDF-Extract-Kit full pipeline",
        input_schema={
            "pdf_dir": "str",
            "pdf_files": "List[str]",
            "output_dir": "str",
            "merge_markdown": "bool",
            "extract_images": "bool",
        },
        output_schema={
            "parsed_papers": "List[Dict]",
            "parse_errors": "List[Dict]",
            "stats": "Dict",
        },
        tags={"parser", "pdf", "gpu"},
        factory=_make_factory(*_ADAPTERS["pdf_kit_parse"]),
    ))

    specs.append(ModuleSpec(
        name="pdf_kit_parse_batch",
        display_name="PDF-Extract-Kit Batch Parser",
        description="Batch-parse PDFs through one PEK cold-start using explicit 1:1 pdf_paths/output_dirs pairing",
        input_schema={
            "pdf_paths": "List[str]",
            "output_dirs": "List[str]",
            "extract_images": "bool",
        },
        output_schema={
            "parsed_papers": "List[Dict]",
            "parse_errors": "List[Dict]",
            "stats": "Dict",
        },
        tags={"parser", "pdf", "gpu", "batch"},
        factory=_make_factory(*_ADAPTERS["pdf_kit_parse_batch"]),
    ))

    specs.append(ModuleSpec(
        name="pek_start",
        display_name="PEK Daemon Start",
        description="Start (or attach to) a long-running PEK daemon so models stay resident across many parse calls",
        input_schema={
            "state_dir": "str",
            "device": "str",
            "config_path": "str",
            "ready_timeout_seconds": "float",
        },
        output_schema={
            "socket_path": "str",
            "pid": "int",
            "status": "str",
            "state_dir": "str",
            "reused": "bool",
        },
        tags={"parser", "pdf", "gpu", "lifecycle"},
        factory=_make_factory(*_ADAPTERS["pek_start"]),
    ))

    specs.append(ModuleSpec(
        name="pek_parse",
        display_name="PEK Daemon Parse",
        description="Parse one PDF via a running PEK daemon (RPC over Unix socket); does not start or stop the daemon",
        input_schema={
            "pdf_path": "str",
            "pdf_files": "List[str]",
            "output_dir": "str",
            "socket_path": "str",
            "state_dir": "str",
            "timeout_seconds": "float",
        },
        output_schema={
            "parsed_papers": "List[Dict]",
            "parse_errors": "List[Dict]",
            "stats": "Dict",
        },
        tags={"parser", "pdf", "gpu", "rpc"},
        factory=_make_factory(*_ADAPTERS["pek_parse"]),
    ))

    specs.append(ModuleSpec(
        name="pek_stop",
        display_name="PEK Daemon Stop",
        description="Stop the PEK daemon (graceful RPC, then SIGTERM, then SIGKILL) and clear state.json",
        input_schema={
            "state_dir": "str",
            "grace_seconds": "float",
        },
        output_schema={
            "stopped": "bool",
            "method": "str",
            "pid": "int",
        },
        tags={"parser", "pdf", "lifecycle"},
        factory=_make_factory(*_ADAPTERS["pek_stop"]),
    ))

    _EXPERIMENT_PAPER_SPECS = [
        ("experiment_plan_generator", "Experiment Plan Generator", "Generate experiment plans from research ideas",
         {"content": "str", "content_type": "str", "feedback": "str", "resource_config_path": "str"},
         {"experiment_plan": "str", "persistence_info": "Dict"}),
        ("experiment_plan_evaluator", "Experiment Plan Evaluator", "Evaluate experiment plan quality and route",
         {"experiment_plan": "str", "original_content": "str"},
         {"score": "float", "evaluation_summary": "str", "_route": "str", "_score": "float", "persistence_info": "Dict"}),
        ("experiment_plan_reviser", "Experiment Plan Reviser", "Revise experiment plan based on feedback",
         {"experiment_plan": "str", "original_content": "str", "evaluation_feedback": "str"},
         {"revised_plan": "str", "persistence_info": "Dict"}),
        ("experiment_resource_checker", "Experiment Resource Checker", "Check if experiment resources are available locally",
         {"experiment_plan": "str"},
         {"resource_estimate": "Dict", "_route": "str", "_score": "float", "persistence_info": "Dict"}),
        ("experiment_executor_opencode", "Experiment Executor (OpenCode)", "Execute experiments via opencode in isolated workspace",
         {"experiment_plan": "str", "resource_context": "Dict"},
         {"experiment_results": "Dict", "execution_log": "str", "workdir": "str", "session_id": "str", "persistence_info": "Dict"}),
        ("paper_cli_runner", "Paper CLI Runner (OpenCode)", "Delegate Phase-4 paper writing to paper_cli (opencode session)",
         {"title": "str", "idea": "Any", "experiment_report": "str", "experiment_results": "Dict", "paper_metadata": "Dict"},
         {"pdf_path": "str", "workspace": "str", "run_id": "str", "paper_cli_rc": "int", "persistence_info": "Dict"}),
        ("experiment_runner_cli", "Experiment Runner CLI (OpenCode)", "Run an experiment via experiment_runner_cli (opencode subprocess)",
         {"experiment_plan": "str", "idea": "Any", "resource_constraint": "str"},
         {"success": "bool", "experiment_results": "Dict", "execution_log": "str", "workspace": "str", "run_id": "str", "runner_cli_rc": "int", "persistence_info": "Dict"}),
        ("experiment_verifier_cli", "Experiment Verifier CLI (OpenCode)", "Judge runner outputs and emit pass/retry/fail verdict",
         {"experiment_plan": "str", "runner_workspace": "str"},
         {"verdict": "str", "score": "float", "reasoning": "str", "evidence": "List", "improvement_suggestions": "List", "success": "bool", "workspace": "str", "run_id": "str", "persistence_info": "Dict"}),
        ("experiment_goal_evaluator", "Experiment Goal Evaluator", "Evaluate if experiment results meet original goals",
         {"idea": "str", "experiment_plan": "str", "experiment_results": "Dict"},
         {"evaluation": "str", "suggestions": "str", "_route": "str", "_score": "float", "persistence_info": "Dict"}),
        ("experiment_report_generator", "Experiment Report Generator", "Generate experiment report in Markdown",
         {"idea": "str", "experiment_plan": "str", "experiment_results": "Dict", "goal_evaluation": "str"},
         {"report": "str", "report_path": "str", "persistence_info": "Dict"}),
        ("chart_code_generator", "Chart Code Generator", "Generate and execute scientific chart code",
         {"experiment_results": "Dict", "experiment_plan": "str", "chart_requirements": "str"},
         {"chart_paths": "List[str]", "chart_code": "str", "persistence_info": "Dict"}),
        ("experiment_persist", "Experiment Persist", "Persist experiment data to SQLite",
         {"experiment_results": "Dict", "experiment_plan": "str", "session_id": "str"},
         {"persist_id": "str", "db_path": "str"}),
        ("image_prompt_generator", "Image Prompt Generator", "Generate image creation prompts from context",
         {"context": "str", "language": "str", "image_type": "str", "style_hint": "str"},
         {"prompts": "List[Dict]", "persistence_info": "Dict"}),
        ("image_generator", "Image Generator", "Generate images via gpt-image-2 API or placeholder",
         {"prompt": "str", "style": "str", "aspect_ratio": "str"},
         {"image_path": "str", "image_metadata": "Dict", "persistence_info": "Dict"}),
        ("image_persist", "Image Persist", "Persist images with metadata to DB",
         {"image_path": "str", "image_type": "str", "prompt_text": "str", "language": "str", "style": "str", "source_node": "str", "session_id": "str"},
         {"persist_id": "str", "stored_path": "str", "db_path": "str"}),
        ("paper_outline_generator", "Paper Outline Generator", "Generate paper structure outline",
         {"idea": "str", "experiment_report": "str", "references": "List[Dict]"},
         {"outline": "List[Dict]", "persistence_info": "Dict"}),
        ("paper_section_writer", "Paper Section Writer", "Write paper sections in LaTeX by section type",
         {"outline_section": "Dict", "context": "str", "section_type": "str", "references": "List[Dict]"},
         {"section_content": "str", "section_type": "str", "persistence_info": "Dict"}),
        ("paper_coherence_checker", "Paper Coherence Checker", "Check cross-section consistency and route",
         {"all_sections": "List[Dict]", "outline": "List[Dict]"},
         {"issues": "List[Dict]", "_route": "str", "_score": "float", "persistence_info": "Dict"}),
        ("paper_formatter", "Paper Formatter", "Assemble LaTeX document",
         {"all_sections": "List[Dict]", "images": "List[Dict]", "bibtex": "str", "template": "str"},
         {"tex_path": "str", "pdf_path": "str", "persistence_info": "Dict"}),
        ("paper_persist", "Paper Persist", "Persist paper artifacts to DB",
         {"tex_path": "str", "pdf_path": "str", "sections": "List[Dict]", "images": "List[Dict]", "session_id": "str"},
         {"persist_id": "str", "db_path": "str"}),
        ("reference_collector", "Reference Collector", "Retrieve candidate references from local DB",
         {"topic": "str", "method_keywords": "List[str]", "top_k": "int"},
         {"candidates": "List[Dict]", "persistence_info": "Dict"}),
        ("reference_gap_analyzer", "Reference Gap Analyzer", "Analyze citation gaps in paper sections",
         {"paper_sections": "List[Dict]", "candidate_references": "List[Dict]"},
         {"citation_gaps": "List[Dict]", "persistence_info": "Dict"}),
        ("bibtex_generator", "BibTeX Generator", "Generate .bib file from confirmed references",
         {"confirmed_references": "List[Dict]"},
         {"bib_path": "str", "citation_keys": "Dict", "persistence_info": "Dict"}),
        ("citation_inserter", "Citation Inserter", "Insert \\cite{} markers into paper sections",
         {"paper_sections": "List[Dict]", "citation_gaps": "List[Dict]", "citation_keys": "Dict"},
         {"annotated_sections": "List[Dict]", "persistence_info": "Dict"}),
        ("reference_integrity_checker", "Reference Integrity Checker", "Check citation completeness (tex <-> bib)",
         {"paper_tex": "str", "bib_path": "str"},
         {"issues": "List[Dict]", "_route": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _EXPERIMENT_PAPER_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"experiment_paper"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    specs.append(ModuleSpec(
        name="paper_summary_search",
        display_name="Paper Summary Search",
        description="Search paper summary by title across multiple sources (S2, CrossRef, OpenAlex, etc.) in fallback order",
        input_schema={"title": "str", "keywords": "List[str]"},
        output_schema={"metadata": "Dict", "source": "str", "paper_count": "int", "_route": "str"},
        tags={"search", "multi_source"},
        factory=_make_factory(*_ADAPTERS["paper_summary_search"]),
    ))

    _PIPELINE_GATE_SPECS = [
        ("pdf_queue_feeder", "PDF Queue Feeder", "Dispatch PDF paths one at a time from a persistent queue",
         {"pdf_list_path": "str", "pdf_list": "List[str]"},
         {"pdf_files": "List[str]", "pdf_path": "str", "queue_index": "int", "_route": "str"}),
        ("parsed_folder_feeder", "Parsed Folder Feeder",
         "Dispatch already-parsed PDF result folders one at a time from a resumable queue",
         {"parsed_root": "str", "state_dir": "str", "id_whitelist": "List[str]"},
         {"folder_path": "str", "paper_id": "str", "queue_index": "int",
          "queue_remaining": "int", "_route": "str"}),
        ("parsed_folder_loader", "Parsed Folder Loader",
         "Load a previously-parsed PDF folder ({paper_id}.json + {paper_id}.md) into the pdf_kit_parse output schema",
         {"folder_path": "str", "paper_id": "str"},
         {"parsed_papers": "List[Dict]", "parse_errors": "List[Dict]", "stats": "Dict"}),
        ("title_persist", "Title Persist",
         "Write the validated paper title to <folder>/title.md so it survives DB resets / folder moves",
         {"folder_path": "str", "title": "str", "paper_id": "str"},
         {"title_path": "str", "wrote": "bool"}),
        ("parsed_folder_freshness_feeder", "Parsed Folder Freshness Feeder",
         "Rescan a parsed root and dispatch folders that satisfy require_files / forbid_files / min_quiet_seconds rules",
         {"parsed_root": "str"},
         {"folder_path": "str", "paper_id": "str", "queue_remaining_estimate": "int", "_route": "str"}),
        ("title_loader", "Title Loader",
         "Read the persisted title from <folder>/title.md (no LLM calls)",
         {"folder_path": "str", "paper_id": "str"},
         {"title": "str", "paper_id": "str", "_route": "str"}),
        ("paper_id_allocator", "Paper ID Allocator",
         "Reserve a paper_id in papers.db at parse-persist time and write paper_id.txt to the folder",
         {"parsed_papers": "List[Dict]", "paper_id": "str", "output_dir": "str"},
         {"paper_id": "str", "output_dir": "str", "id_path": "str", "claimed": "bool",
          "already_persisted": "bool", "_route": "str"}),
        ("pdf_mover", "PDF Mover",
         "Move a parsed PDF from downloaded_papers/ to parsedpaper/ preserving relative subdirs",
         {"parsed_papers": "List[Dict]", "pdf_path": "str"},
         {"moved": "bool", "source_path": "str", "target_path": "str"}),
        ("parse_result_gate", "Parse Result Gate", "Check whether pdf_kit_parse produced valid results",
         {"parsed_papers": "List[Dict]", "parse_errors": "List[Dict]"},
         {"_route": "str", "parsed_papers": "List[Dict]", "paper_id": "str"}),
        ("title_result_gate", "Title Result Gate", "Check whether title_extractor produced a valid title",
         {"titles": "List[Dict]", "paper_id": "str"},
         {"_route": "str", "validated_title": "str", "paper_id": "str"}),
        ("summary_result_gate", "Summary Result Gate", "Check whether paper_summary_search returned valid metadata",
         {"metadata": "Dict", "source": "str", "paper_id": "str"},
         {"_route": "str", "metadata": "Dict", "source": "str", "paper_id": "str"}),
        ("id_align_gate", "ID Align Gate", "Align paper_id between parse result and search result",
         {"metadata": "Dict", "paper_id": "str"},
         {"metadata": "Dict", "paper_id": "str", "original_paper_id": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _PIPELINE_GATE_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"pipeline", "gate"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    specs.append(ModuleSpec(
        name="pdf_parser",
        display_name="PDF Parser",
        description="Parse PDF files into structured content using configurable engines",
        input_schema={
            "pdf_dir": "str",
            "pdf_files": "List[str]",
            "metadata": "List[Dict]",
            "engine": "str",
            "max_concurrent": "int",
        },
        output_schema={
            "papers": "List[Dict]",
            "paper_count": "int",
            "parse_errors": "List[str]",
        },
        tags={"parser", "pdf"},
        factory=_make_factory(*_ADAPTERS["pdf_parser"]),
    ))

    specs.append(ModuleSpec(
        name="title_extractor",
        display_name="Title Extractor",
        description="Extract exact paper titles from parsed content using LLM consensus",
        input_schema={
            "papers": "List[Dict]",
        },
        output_schema={
            "titles": "List[Dict]",
            "paper_count": "int",
            "success_count": "int",
            "fail_count": "int",
        },
        tags={"parser", "llm_required"},
        factory=_make_factory(*_ADAPTERS["title_extractor"]),
    ))

    _ITERATION_CONTROLLER_SPECS = [
        ("threshold_iteration_controller", "Threshold Iteration Controller",
         "Continue iterating until score >= threshold or max attempts reached",
         {"_score": "float", "_iteration_attempt": "int"},
         {"_route": "str", "_score": "float", "_metadata": "Dict"}),
        ("patience_iteration_controller", "Patience Iteration Controller",
         "Continue while score improves; exit after N rounds without improvement",
         {"_score": "float", "_iteration_prev_score": "float", "_iteration_no_improve": "int"},
         {"_route": "str", "_score": "float", "_metadata": "Dict"}),
        ("improving_iteration_controller", "Improving Iteration Controller",
         "Continue while score is still improving; exit when improvement stalls",
         {"_score": "float", "_iteration_prev_score": "float"},
         {"_route": "str", "_score": "float", "_metadata": "Dict"}),
        ("llm_iteration_controller", "LLM Iteration Controller",
         "Use LLM to judge whether iteration should continue",
         {"_score": "float", "_iteration_attempt": "int", "_iteration_history": "List"},
         {"_route": "str", "_score": "float", "_metadata": "Dict"}),
        ("multi_criteria_iteration_controller", "Multi-Criteria Iteration Controller",
         "Multi-dimensional weighted scoring for iteration control",
         {"_score": "float", "_iteration_attempt": "int"},
         {"_route": "str", "_score": "float", "_metadata": "Dict"}),
        ("result_aggregator", "Result Aggregator",
         "Domain-aware merge of multiple upstream outputs with configurable strategies",
         {"_merged_upstream": "Dict"},
         {"aggregated": "Dict", "source_count": "int"}),
        ("quality_scorer", "Quality Scorer",
         "Evaluate upstream output and emit routing decision via quality thresholds",
         {"score": "float"},
         {"_route": "str", "_score": "float", "quality_score": "float", "quality_route": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _ITERATION_CONTROLLER_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"flow_control", "iteration"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _AUTO_IDEA_SPECS = [
        ("paper_summary_agent", "Paper Summary Agent",
         "Extract key idea-inspiring summary from a single paper via LLM",
         {"paper": "Dict"},
         {"summary": "str", "key_innovations": "List[str]", "open_problems": "List[str]",
          "transferable_techniques": "List[str]", "paper_title": "str"}),
        ("summary_accumulator", "Summary Accumulator",
         "Accumulate paper summaries until target count, then merge and route",
         {"summary": "str", "key_innovations": "List[str]", "open_problems": "List[str]",
          "transferable_techniques": "List[str]", "paper_title": "str"},
         {"_route": "str", "merged_summaries": "str", "previous_ideas": "List[Dict]",
          "current_count": "int", "target_count": "int"}),
        ("idea_evolution_agent", "Idea Evolution Agent",
         "Generate evolving research ideas from merged summaries and previous ideas (V100 32GB constraint)",
         {"merged_summaries": "str", "previous_ideas": "List[Dict]", "resource_constraint": "str"},
         {"ideas": "List[Dict]", "round_report": "str"}),
        ("round_controller", "Round Controller",
         "Count idea generation rounds and route continue/exit, sync previous_ideas to accumulator",
         {"ideas": "List[Dict]", "round_report": "str"},
         {"_route": "str", "ideas": "List[Dict]", "round_number": "int"}),
        ("best_idea_selector", "Best Idea Selector",
         "Select the highest-scoring idea from ranked ideas",
         {"ranked_ideas": "List[Dict]", "ideas": "List[Dict]"},
         {"best_idea": "Dict", "idea_title": "str", "idea_description": "str",
          "selected_score": "float", "all_ideas_count": "int"}),
        ("paper_md_assembler", "Paper MD Assembler",
         "Assemble final paper markdown with chart image references",
         {"markdown_content": "any", "chart_paths": "List[str]", "idea": "Dict"},
         {"final_md_path": "str", "final_md_content": "str", "chart_count": "int"}),
        ("experiment_success_gate", "Experiment Success Gate",
         "Gate node: retry failed experiments up to N times, then skip to paper generation",
         {"experiment_results": "Dict", "execution_log": "str"},
         {"_route": "str", "retry_count": "int", "experiment_success": "bool"}),
        ("incremental_persistence", "Incremental Persistence",
         "Incrementally append each node output to a shared JSONL file for full pipeline auditing",
         {"data": "any"},
         {"persisted": "bool", "file_path": "str"}),
     ]
    for name, display, desc, in_schema, out_schema in _AUTO_IDEA_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"auto_idea", "pipeline"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _KG_INDEX_SPECS = [
        ("kg_extract", "KG Extract",
         "Extract knowledge units from raw text via LLM (Phase 1)",
         {"content": "str", "source_type": "str", "source_id": "str"},
         {"units": "List[Dict]", "unit_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_dedup", "KG Dedup",
         "Deduplicate units by content_hash (Phase 2)",
         {"units": "List[Dict]", "source_type": "str", "source_id": "str"},
         {"new_units": "List[Dict]", "duplicate_units": "List[Dict]", "new_count": "int", "dup_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_embed", "KG Embed",
         "Compute embeddings for chunk_text + abstract_summary (Phase 3a)",
         {"new_units": "List[Dict]", "source_type": "str", "source_id": "str"},
         {"embedded_units": "List[Dict]", "embed_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_write_node", "KG Write Node",
         "Write KGNode + Provenance + embeddings to Neo4j (Phase 3b)",
         {"embedded_units": "List[Dict]", "source_type": "str", "source_id": "str"},
         {"new_node_ids": "List[str]", "dup_appended_count": "int", "total_node_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_build_internal_edge", "KG Internal Edge",
         "Discover relations within same-batch units via LLM (Phase 4)",
         {"units": "List[Dict]", "source_type": "str", "source_id": "str"},
         {"relations": "List[Dict]", "relation_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_build_struct_edge", "KG Struct Edge",
         "Build edges from SQLite foreign keys, zero LLM (Phase 5)",
         {"new_node_ids": "List[str]", "source_type": "str", "source_id": "str"},
         {"struct_edges": "List[Dict]", "struct_edge_count": "int", "source_type": "str", "source_id": "str"}),
        ("kg_build_semantic_edge", "KG Semantic Edge",
         "Build semantic edges via triple-filter + LLM eval (Phase 6)",
         {"new_node_ids": "List[str]", "source_type": "str", "source_id": "str"},
         {"semantic_edges": "List[Dict]", "semantic_edge_count": "int", "candidate_stats": "Dict", "source_type": "str", "source_id": "str"}),
        ("kg_random_walk", "KG Random Walk",
         "Discover remote relations via weighted random walk (Phase 7)",
         {"new_node_ids": "List[str]", "source_type": "str", "source_id": "str"},
         {"walk_edges": "List[Dict]", "walk_edge_count": "int", "walk_stats": "Dict", "source_type": "str", "source_id": "str"}),
        ("kg_retrospect", "KG Retrospect",
         "Discover missing edges between neighbors (Phase 8)",
         {"new_node_ids": "List[str]", "source_type": "str", "source_id": "str"},
         {"retrospect_edges": "List[Dict]", "retrospect_edge_count": "int", "candidate_pair_count": "int", "source_type": "str", "source_id": "str"}),
    ]
    for name, display, desc, in_schema, out_schema in _KG_INDEX_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"kg", "kg_index"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _KG_QUERY_SPECS = [
        ("kg_vector_search", "KG Vector Search",
         "Search similar KGNodes via Neo4j vector index",
         {"query": "str", "top_k": "int"},
         {"results": "List[Dict]", "result_count": "int"}),
        ("kg_graph_traverse", "KG Graph Traverse",
         "Traverse subgraph from seed nodes in Neo4j",
         {"node_ids": "List[str]", "max_hops": "int"},
         {"nodes": "List[Dict]", "edges": "List[Dict]", "provenances": "List[Dict]", "hop_reached": "int"}),
        ("kg_nl_query", "KG NL Query",
         "Natural language question to search strategy to answer",
         {"question": "str"},
         {"answer": "str", "sources_used": "List[Dict]", "traversal_path": "List[Dict]", "confidence": "float"}),
        ("kg_abstract_enrich", "KG Abstract Enrich",
         "Enrich abstract by finding similar full-text papers",
         {"abstract": "str"},
         {"enriched_context": "str", "related_methods": "List[Dict]", "related_experiments": "List[Dict]", "related_code": "List[Dict]", "source_papers": "List[Dict]"}),
        ("kg_synthesize", "KG Synthesize",
         "Synthesize new ideas from graph traversal",
         {"seed_idea": "str"},
         {"synthesized_ideas": "List[Dict]", "source_paths": "List[Dict]", "idea_count": "int"}),
    ]
    for name, display, desc, in_schema, out_schema in _KG_QUERY_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"kg", "kg_query"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _KG_OPS_SPECS = [
        ("kg_crud", "KG CRUD",
         "CRUD operations on KGNode / Provenance / RELATED",
         {"operation": "str", "data": "Dict"},
         {"result": "Dict", "success": "bool"}),
        ("kg_rebuild", "KG Rebuild",
         "Full rebuild of the Neo4j knowledge graph from SQLite",
         {"db_paths": "Dict"},
         {"total_nodes": "int", "total_edges": "int", "total_provenances": "int", "duration_seconds": "float", "errors": "List[str]"}),
        ("kg_prune", "KG Prune",
         "Prune edges by degree/weight/decay",
         {"max_edges_per_node": "int", "min_weight": "float", "dry_run": "bool"},
         {"pruned_count": "int", "pruned_by_degree": "int", "pruned_by_weight": "int", "pruned_by_decay": "int", "total_edges_before": "int", "total_edges_after": "int"}),
    ]
    for name, display, desc, in_schema, out_schema in _KG_OPS_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"kg", "kg_ops"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    _PAPER_INTRA_INDEX_SPECS = [
        ("paper_db_reader", "Paper DB Reader",
         "Read all sections / tables / formulas / images of one paper from papers.db (read-only).",
         {"paper_id": "str"},
         {"paper_id": "str", "paper_meta": "Dict", "sections": "List[Dict]",
          "tables": "List[Dict]", "formulas": "List[Dict]", "images": "List[Dict]",
          "found": "bool"}),
        ("paper_intra_index", "Paper Intra Index",
         "Build the intra-paper KG index from a PaperBundle: extract units, "
         "write nodes, mechanism edges, LLM round 1 + round 2 stitching.",
         {"paper_id": "str", "sections": "List[Dict]", "tables": "List[Dict]",
          "formulas": "List[Dict]", "images": "List[Dict]", "paper_meta": "Dict"},
         {"paper_id": "str", "unit_node_ids": "List[str]",
          "section_node_ids": "List[str]", "element_node_ids": "List[str]",
          "mechanism_edge_count": "int", "round1_edge_count": "int",
          "round2_edge_count": "int", "round1_batches": "int",
          "round2_pair_count": "int", "round2_skipped": "bool",
          "errors": "List[str]"}),
        ("paper_intra_index_incremental", "Paper Intra Index Incremental",
         "Refresh one paper's intra-paper index after upstream content changes.",
         {"paper_id": "str"},
         {"paper_id": "str", "new_section_count": "int", "new_unit_count": "int",
          "next_section_edges_rewritten": "int", "mechanism_edge_count": "int",
          "round2_edge_count": "int", "round2_pair_count": "int",
          "errors": "List[str]", "skipped": "bool"}),
        ("kg_cross_paper_discover", "KG Cross-Paper Discover",
         "Find cross-paper :RELATED edges between paper_unit nodes via "
         "vector kNN candidate filter + LLM relation evaluation.",
         {"paper_id": "str", "top_k_per_unit": "int", "min_confidence": "float",
          "max_context_tokens": "int", "max_evaluations": "int"},
         {"paper_id": "str", "unit_count": "int",
          "candidate_pair_count": "int", "evaluated_pair_count": "int",
          "cross_paper_edge_count": "int", "llm_calls": "int",
          "errors": "List[str]", "skipped": "bool"}),
    ]
    for name, display, desc, in_schema, out_schema in _PAPER_INTRA_INDEX_SPECS:
        specs.append(ModuleSpec(
            name=name,
            display_name=display,
            description=desc,
            input_schema=in_schema,
            output_schema=out_schema,
            tags={"kg", "kg_index", "paper"},
            factory=_make_factory(*_ADAPTERS[name]),
        ))

    return specs


def register_all_modules(registry: ModuleRegistry) -> None:
    for spec in get_all_module_specs():
        registry.register(spec)


__all__ = [
    "register_all_modules",
    "get_all_module_specs",
]
