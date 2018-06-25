import json
from flywheel_bids.curate_bids import main_with_args

if __name__ == '__main__':

    # Grab Config
    CONFIG_FILE_PATH = '/flywheel/v0/config.json'
    with open(CONFIG_FILE_PATH) as config_file:
        config = json.load(CONFIG_FILE)

    api_key = config['inputs']['api_key']['key']
    session_id = config['destination']['id']
    reset = config['config']['reset']

    main_with_args(api_key, session_id, reset)