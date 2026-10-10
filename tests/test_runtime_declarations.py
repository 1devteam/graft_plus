from graft_plus.graph import build_graph


def _edge(graph, source, target, kind):
    return any(
        edge["from"] == source and edge["to"] == target and edge["type"] == kind
        for edge in graph["edges"]
    )


def test_literal_runtime_declarations_become_facts_without_adjudication(tmp_path):
    (tmp_path / "app.py").write_text(
        "def qualify(payload):\n"
        "    return payload\n\n"
        "def register():\n"
        "    return ActionDefinition(\n"
        "        name='sales.qualify',\n"
        "        handler=qualify,\n"
        "        provider='local_sales',\n"
        "        input_model=SalesLeadInput,\n"
        "        side_effect_class=SideEffectClass.INTERNAL_READ,\n"
        "        credential_requirement=CredentialRequirement(provider='crm'),\n"
        "    )\n\n"
        "JOB = BusinessJob(\n"
        "    job_key='qualify_lead',\n"
        "    required_inputs=('company_name', 'research_summary'),\n"
        "    produced_outputs=('qualification_score',),\n"
        "    candidate_actions=('sales.qualify',),\n"
        "    dependencies=(JobDependency(job_key='research_company', kind='hard'),),\n"
        "    maturity='active',\n"
        ")\n"
    )

    graph = build_graph(subject=tmp_path)
    nodes = {node["id"]: node for node in graph["nodes"]}

    assert graph["schema_version"] == "1.14"
    assert nodes["job:qualify_lead"]["type"] == "business_job"
    assert nodes["action:sales.qualify"]["type"] == "runtime_action"
    assert nodes["artifact:qualification_score"]["type"] == "runtime_artifact"
    assert nodes["input:company_name"]["type"] == "runtime_input"
    assert nodes["input:research_summary"]["type"] == "runtime_input"
    assert nodes["input-contract:SalesLeadInput"]["type"] == "runtime_input_contract"
    assert nodes["credential-requirement:sales.qualify"]["type"] == "credential_requirement"
    assert nodes["provider:local_sales"]["type"] == "runtime_provider"
    assert nodes["provider:crm"]["type"] == "runtime_provider"
    assert nodes["side-effect-class:SideEffectClass.INTERNAL_READ"]["type"] == "side_effect_class"
    assert nodes["job:research_company"]["type"] == "business_job_reference"

    assert _edge(graph, "job:qualify_lead", "action:sales.qualify", "candidate_action")
    assert _edge(graph, "artifact:qualification_score", "job:qualify_lead", "produced_by")
    assert _edge(graph, "job:qualify_lead", "input:company_name", "requires_input")
    assert _edge(
        graph,
        "action:sales.qualify",
        "input-contract:SalesLeadInput",
        "declares_input_model",
    )
    assert _edge(
        graph,
        "action:sales.qualify",
        "side-effect-class:SideEffectClass.INTERNAL_READ",
        "declares_side_effect_class",
    )
    assert _edge(graph, "action:sales.qualify", "provider:local_sales", "uses_provider")
    assert _edge(
        graph,
        "action:sales.qualify",
        "credential-requirement:sales.qualify",
        "requires_credential",
    )
    assert _edge(
        graph,
        "credential-requirement:sales.qualify",
        "provider:crm",
        "credential_for_provider",
    )
    assert _edge(graph, "job:qualify_lead", "job:research_company", "depends_on_job")

    assert "decision" not in graph
    assert "risk" not in graph
    assert "proof_selection" not in graph
    assert graph["facts"]["runtime_declaration_node_counts"]["business_job"] == 1


def test_job_inputs_resolve_to_artifacts_when_an_output_is_declared_elsewhere(tmp_path):
    (tmp_path / "jobs.py").write_text(
        "RESEARCH = JobDefinition(\n"
        "    key='research',\n"
        "    required_inputs=('company_name',),\n"
        "    produced_outputs=('research_summary',),\n"
        "    candidate_actions=(),\n"
        ")\n\n"
        "QUALIFY = JobDefinition(\n"
        "    key='qualify',\n"
        "    required_inputs=('research_summary',),\n"
        "    produced_outputs=('score',),\n"
        "    candidate_actions=(),\n"
        ")\n"
    )

    graph = build_graph(subject=tmp_path)

    assert _edge(graph, "job:qualify", "artifact:research_summary", "requires_artifact")
    assert not any(node["id"] == "input:research_summary" for node in graph["nodes"])
