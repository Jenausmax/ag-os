
def can_access(requester: str, owner: str, scope: str, shared_with: list[str]) -> bool:
    if requester == "master":
        return True
    if requester == owner:
        return True
    if scope == "global":
        return True
    if scope == "shared" and requester in shared_with:
        return True
    return False
