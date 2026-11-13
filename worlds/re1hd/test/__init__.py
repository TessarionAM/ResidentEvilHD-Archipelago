from test.bases import WorldTestBase


class RE1HDTestBase(WorldTestBase):
    game = "Resident Evil HD Remaster"
    # The key-chain tests check the FULL logic, so every pickup is a check here.
    # TestOnlyDetectedPickups covers the default "only detected pickups" mode.
    options = {"only_detected_pickups": False}
