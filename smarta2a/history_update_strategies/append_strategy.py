
class AppendStrategy:
    """Default append behavior"""
    def update_history(self, existing, new):
        return existing + new