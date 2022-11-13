import random, string, sys
import requests
import logging

api_host = ''
api_key = ''

class MailcowApiError(Exception):
    '''The rules of the mailcow game were not followed'''

def __post_request(url, json_data):
    api_url = f"{api_host}/{url}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}

    req = requests.post(api_url, headers=headers, json=json_data)
    rsp = req.json()
    req.close()

    if isinstance(rsp, list):
        rsp = rsp[0]

    if not "type" in rsp or not "msg" in rsp:
        raise MailcowApiError(f"API {url}: got response without type or msg from Mailcow API")
    
    if rsp['type'] != 'success':
        raise MailcowApiError(f"API {url}: {rsp['type']} - {rsp['msg']}")

def add_user(uid, maildomain, name, active):
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
    json_data = {
        'local_part':uid,
        'domain':maildomain,
        'name':name,
        'password':password,
        'password2':password,
        "active": 1 if active else 0
    }

    __post_request('api/v1/add/mailbox', json_data)

def edit_user(uid, maildomain, active=None, name=None):
    attr = {}
    if (active is not None):
        attr['active'] = 1 if active else 0
    if (name is not None):
        attr['name'] = name

    json_data = {
        'items': [uid + '@' + maildomain],
        'attr': attr
    }

    __post_request('api/v1/edit/mailbox', json_data)

def __delete_user(uid, maildomain):
    json_data = [uid + '@' + maildomain]

    __post_request('api/v1/delete/mailbox', json_data)

def check_user(uid, maildomain):
    url = f"{api_host}/api/v1/get/mailbox/{uid}@{maildomain}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}
    req = requests.get(url, headers=headers)
    rsp = req.json()
    req.close()
    
    if not isinstance(rsp, dict):
        raise MailcowApiError("API get/mailbox: got response of a wrong type")

    if (not rsp):
        return (False, False, None)

    if 'active_int' not in rsp and rsp['type'] == 'error':
        raise MailcowApiError(f"API {url}: {rsp['type']} - {rsp['msg']}")
    
    return (True, bool(rsp['active_int']), rsp['name'])

def check_domain(maildomain):
    url = f"{api_host}/api/v1/get/domain/{maildomain}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}
    req = requests.get(url, headers=headers)
    rsp = req.json()
    req.close()

    if req.status_code != 200:
        logging.info (f"Mail domain {maildomain} query failed with status {req.status_code}")
        return False
    
    if isinstance(rsp, list):
        if (not rsp or len(rsp) == 0):
            return False
        rsp = rsp[0]

    if not isinstance(rsp, dict):
        return False

    if 'active' not in rsp or not bool(rsp['active']):
        return False

    if 'backupmx' in rsp and bool(rsp['backupmx']):
        return False
    
    return True
