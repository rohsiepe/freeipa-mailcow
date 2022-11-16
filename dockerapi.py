import string, sys
import requests
import logging
import json

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

project_name = 'mailcowdockerized'

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

def get_container_id(servicename):
    rsp = __get_request("containers/json")
    if isinstance(rsp, dict):
        for id, container in rsp.items():
            if 'Config' in container and 'Id' in container:
                containercfg = container.get('Config')
                if 'Labels' in containercfg:
                    containerlabels = containercfg.get('Labels')
                    if 'com.docker.compose.service' in containerlabels and 'com.docker.compose.project' in containerlabels:
                        containerservice = containerlabels.get('com.docker.compose.service')
                        containerproject = containerlabels.get('com.docker.compose.project').lower()
                        if containerproject == project_name.lower() and containerservice == servicename:
                            return container.get('Id').strip()
    return ''

def get_sogo_id():
    return get_container_id('sogo-mailcow')

def get_dovecot_id():
    return get_container_id('dovecot-mailcow')

def test2(container):
    if 'Config' in container and 'Id' in container:
        containercfg = container.get('Config')
        if 'Labels' in containercfg:
            containerlabels = containercfg.get('Labels')
            if 'com.docker.compose.service' in containerlabels and 'com.docker.compose.project' in containerlabels:
                containerid = container.get('Id').strip()
                containerservice = containerlabels.get('com.docker.compose.service')
                containerproject = containerlabels.get('com.docker.compose.project').lower()
                if containerproject == project_name.lower():
                    logging.info(f"{containerid} => {containerservice}, {containerproject}=={project_name.lower()}")
                else:
                    logging.info(f"{containerid} => {containerservice}, {containerproject}!={project_name.lower()}")


def test():
    rsp = __get_request("containers/json")
    #logging.info (f"Containers info:\n{json.dumps(rsp, indent=1)}")
    if isinstance(rsp, dict):
        for id, container in rsp.items():
            test2(container)

    sogoid = get_sogo_id()
    if sogoid == '':
        logging.info("SOGO container not found.")
    else:
        logging.info(f"SOGO container found with id {sogoid}")
    dovecotid = get_dovecot_id()
    if dovecotid == '':
        logging.info("Dovecot container not found.")
    else:
        logging.info(f"Dovecot container found with id {dovecotid}")

