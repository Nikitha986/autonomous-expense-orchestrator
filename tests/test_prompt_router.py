from mcp_server.tools.prompt_router import parse_prompt


def test_parse_upload_and_file():
    p = "Upload these and file for Delhi."
    r = parse_prompt(p)
    assert r["intent"] == "upload_and_file"
    assert r["slots"]["location"].lower() == "delhi"


def test_parse_check_status():
    p = "What is the status of my Delhi report?"
    r = parse_prompt(p)
    assert r["intent"] == "check_status"
    assert r["slots"]["trip"].lower() == "delhi"


def test_parse_manager_list_pending():
    p = "Show the pending expenses for my team members"
    r = parse_prompt(p)
    assert r["intent"] == "manager_list_pending"


def test_parse_manager_approve():
    p = "Approve expense for Rajesh."
    r = parse_prompt(p)
    assert r["intent"] == "manager_approve"
    assert r["slots"]["employee_name"].lower() == "rajesh"
