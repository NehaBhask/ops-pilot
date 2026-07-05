from orchestrator.graph import should_check_incidents


def test_routes_to_incidents_when_repo_critical():
    state = {
        "repo_health": {"status": "critical", "summary": "..."},
        "deploy_status": {"any_environment_failing": False, "summary": "..."},
    }
    assert should_check_incidents(state) == "check_incidents"


def test_skips_incidents_when_everything_healthy():
    state = {
        "repo_health": {"status": "healthy", "summary": "..."},
        "deploy_status": {"any_environment_failing": False, "summary": "..."},
    }
    assert should_check_incidents(state) == "skip_incidents"

def test_routes_to_incidents_when_deploy_failing():
    state = {
        "repo_health": {"status": "healthy", "summary": "..."},
        "deploy_status": {"any_environment_failing": True, "summary": "..."},
    }
    assert should_check_incidents(state) == "check_incidents"

def test_skips_incidents_when_repo_health_missing_and_deploy_ok():
    state = {
        "repo_health": None,
        "deploy_status": {"any_environment_failing": False, "summary": "..."},
    }
    assert should_check_incidents(state) == "skip_incidents"