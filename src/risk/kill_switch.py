class KillSwitch:
    def __init__(self):
        self.engaged = False

    def trigger(self, reason: str = ""):
        self.engaged = True

    def release(self):
        self.engaged = False
