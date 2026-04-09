from memory.access import can_access

def test_master_sees_everything():
    assert can_access(requester="master", owner="jira", scope="private", shared_with=[])

def test_owner_sees_private():
    assert can_access(requester="jira", owner="jira", scope="private", shared_with=[])

def test_other_cannot_see_private():
    assert not can_access(requester="code", owner="jira", scope="private", shared_with=[])

def test_shared_with_specific_agent():
    assert can_access(requester="code", owner="jira", scope="shared", shared_with=["code"])

def test_global_visible_to_all():
    assert can_access(requester="grok", owner="jira", scope="global", shared_with=[])
