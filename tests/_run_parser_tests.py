from mcp_server.tools.prompt_router import parse_prompt


def run():
    p = "Upload these and file for Delhi."
    r = parse_prompt(p)
    assert r["intent"] == "upload_and_file"
    assert r["slots"]["location"].lower() == "delhi"

    p = "What is the status of my Delhi report?"
    r = parse_prompt(p)
    assert r["intent"] == "check_status"
    assert r["slots"]["trip"].lower() == "delhi"

    p = "Show the pending expenses for my team members"
    r = parse_prompt(p)
    assert r["intent"] == "manager_list_pending"

    p = "Approve expense for Rajesh."
    r = parse_prompt(p)
    assert r["intent"] == "manager_approve"
    assert r["slots"]["employee_name"].lower() == "rajesh"

    print('ALL_TESTS_PASSED')


if __name__ == '__main__':
    run()
