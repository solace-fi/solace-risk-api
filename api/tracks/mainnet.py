import os
from api.tracks import BaseRateTracker
from api.utils import *

class MainnetRateTracker(BaseRateTracker):
    def get_name(self):
        return "MainnetRateTracker"

def main(event, context):
    tracker_id = 1
    try:
        tracker_id = int(os.environ['tracker_id'])
    except:
      pass

    try:
        rate_tracker = MainnetRateTracker(chain="1", tracker_id=tracker_id)
        rate_tracker.track()
        return {
            "statusCode": 200,
            "headers": headers
        }
    except Exception as e:
        return handle_error(event, e, 500)

if __name__ == "__main__":
    main(None, None)
