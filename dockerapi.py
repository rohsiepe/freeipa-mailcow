import string, sys
import requests
import logging

class DockerApiError(Exception):
    '''The rules of the mailcow docker game were not followed'''

BASE_URL = "https://dockerapi:443"
REQUEST_TIMEOUT = 10

def __get_request(url):
    api_url = f"{BASE_URL}/{url}"
    headers = {'Content-type': 'application/json'}

    req = requests.get(api_url, verify=False, timeout=REQUEST_TIMEOUT)
    if req.status_code != 200:
        raise DockerApiError(f"DOCKER {url}: unexpected status {req.status_code}")
    
    rsp = req.json()
    req.close()

    if isinstance(rsp, list):
        rsp = rsp[0]
    
    return rsp

def __post_request(url, json_data):
    api_url = f"https://dockerapi:443/{url}"
    headers = {'Content-type': 'application/json'}

    req = requests.post(api_url, verify=False, timeout=REQUEST_TIMEOUT, headers=headers, json=json_data)
    if req.status_code != 200:
        raise DockerApiError(f"DOCKER {url}: unexpected status {req.status_code}")

    rsp = req.json()
    req.close()

    return rsp

def test2(container):
    if 'Config' in container and 'Id' in container:
        containercfg = container.get('Config')
        if 'com.docker.compose.service' in containercfg and 'com.docker.compose.project' in containercfg:
            containerid = container.get('Id')
            containerservice = containercfg.get('com.docker.compose.service')
            containerproject = containercfg.get('com.docker.compose.project')
            logging.info(f"{containerid} => {containerproject} / {containerservice}")


def test():
    rsp = __get_request("containers/json")
    # logging.info (f"Containers info is {rsp}")
    if isinstance(rsp, list):
        for container in rsp:
            if isinstance(container, dict):
                test2(container)
    elif isinstance(rsp, dict):
        test2(rsp)

