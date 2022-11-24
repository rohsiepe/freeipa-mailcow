import sys, os, string, time, datetime
import ldap
import requests
import re

import filedb, api, dockerapi

from string import Template
from pathlib import Path

import logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d.%m.%y %H:%M:%S', level=logging.INFO)

domainstatus = {}

def main():    
    global config 
    config = read_config()

    api.api_host = config['API_HOST']
    api.api_key = config['API_KEY']
    dockerapi.project_name = config['COMPOSE_PROJECT_NAME']

    dockerapi.test()

    passdb_conf = read_dovecot_passdb_conf_template()
    plist_ldap = read_sogo_plist_ldap_template()
    extra_conf = read_dovecot_extra_conf()

    passdb_conf_changed = apply_config('conf/dovecot/ldap/passdb.conf', config_data = passdb_conf)
    extra_conf_changed = apply_config('conf/dovecot/extra.conf', config_data = extra_conf)
    plist_ldap_changed = apply_config('conf/sogo/plist_ldap', config_data = plist_ldap)

    if passdb_conf_changed or extra_conf_changed or plist_ldap_changed:
        logging.info ("One or more config files have been changed")
        if passdb_conf_changed or extra_conf_changed:
            dockerapi.restart_dovecot()
        if plist_ldap_changed:
            dockerapi.restart_sogo()

    while (True):
        if try_sync():
            interval = int(config['SYNC_INTERVAL'])
            logging.info(f"Sync finished, sleeping {interval} seconds before next cycle")
        else:
            interval = int(config['SYNC_INTERVAL'])
            logging.info(f"Sync failed, sleeping {interval} seconds before next cycle")
        time.sleep(interval)

def try_sync():
    try:
        sync()
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('Connection error')
        return False
    except ldap.LDAPError as e:
        logging.exception('LDAP error')
        return False
    except api.MailcowApiError as e:
        logging.exception('Mailcow API error')
        return False
    except:
        logging.exception('An unexpected error occurred.')
        return False

def isaccountenabled(dict):
    if 'nsaccountlock' in dict:
        return (dict['displayName'][0].decode() != 'TRUE')
    return True

def mkfullgroup(grp):
    return 'cn=' \
        + grp \
        + ',cn=groups,cn=accounts,' \
        + config['LDAP_BASE_DN']

def ismemberof(dict, grp):
    fullgroup = mkfullgroup(grp)
    for x in dict['memberOf']:
        if x.decode() == fullgroup:
            return True
    return False

def getmaildomains(dict):
    result = []
    for dom, grp in config['MAIL_DOMAIN'].items():
        if grp == '' or ismemberof(dict, grp):
            result.append(dom)
    return result

def checkmaildomain(maildomain):
    if maildomain not in domainstatus.keys():
        domainstatus[maildomain] = api.check_domain(maildomain)
        if not domainstatus[maildomain]:
            logging.info (f"Mail domain {maildomain} does not exist, skipping")
    else:
        if not domainstatus[maildomain]:
            logging.info (f"Mail domain {maildomain} does not exist (cached), skipping")
    return domainstatus[maildomain]

def sync():
    domainstatus.clear()
    ldap_connector = ldap.initialize(f"{config['LDAP_URI']}")
    ldap_connector.set_option(ldap.OPT_REFERRALS, 0)
    ldap_connector.simple_bind_s(config['LDAP_BIND_DN'], config['LDAP_BIND_DN_PASSWORD'])

    ldap_results = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE, 
                config['LDAP_FILTER'], 
                ['uid', 'displayName', 'nsaccountlock', 'memberOf'])

    ldap_results = map(lambda x: (
        x[1]['uid'][0].decode(),
        getmaildomains(x[1]),
        x[1]['displayName'][0].decode(),
        isaccountenabled(x[1])), ldap_results)

    filedb.session_time = datetime.datetime.now()

    for (uid, maildomains, ldap_name, ldap_active) in ldap_results:
        for maildomain in maildomains:
            if checkmaildomain(maildomain):
                (db_user_exists, db_user_active) = filedb.check_user(uid, maildomain)
                (api_user_exists, api_user_active, api_name) = api.check_user(uid, maildomain)

                email = uid + '@' + maildomain
                unchanged = True

                if not db_user_exists:
                    filedb.add_user(uid, maildomain, ldap_active)
                    (db_user_exists, db_user_active) = (True, ldap_active)
                    logging.info (f"Added filedb user: {email} (Active: {ldap_active})")
                    unchanged = False

                if not api_user_exists:
                    api.add_user(uid, maildomain, ldap_name, ldap_active)
                    (api_user_exists, api_user_active, api_name) = (True, ldap_active, ldap_name)
                    logging.info (f"Added Mailcow user: {email} (Active: {ldap_active})")
                    unchanged = False

                if db_user_active != ldap_active:
                    filedb.user_set_active_to(uid, maildomain, ldap_active)
                    logging.info (f"{'Activated' if ldap_active else 'Deactived'} {email} in filedb")
                    unchanged = False

                if api_user_active != ldap_active:
                    api.edit_user(uid, maildomain, active=ldap_active)
                    logging.info (f"{'Activated' if ldap_active else 'Deactived'} {email} in Mailcow")
                    unchanged = False

                if api_name != ldap_name:
                    api.edit_user(uid, maildomain, name=ldap_name)
                    logging.info (f"Changed name of {email} in Mailcow to {ldap_name}")
                    unchanged = False

                if unchanged:
                    logging.info (f"Checked user {email}, unchanged")

    for email in filedb.get_unchecked_active_emails():
        uid = email.split('@')[0]
        maildomain = email.split('@')[1]       
        (api_user_exists, api_user_active, _) = api.check_user(uid, maildomain)

        if (api_user_exists and api_user_active):
            api.edit_user(uid, maildomain, active=False)
            logging.info (f"Deactivated user {email} in Mailcow, not found in LDAP")
        
        filedb.user_set_active_to(uid, maildomain, False)
        logging.info (f"Deactivated user {email} in filedb, not found in LDAP")

def apply_config(config_file, config_data):
    if os.path.isfile(config_file):
        with open(config_file) as f:
            old_data = f.read()

        if old_data.strip() == config_data.strip():
            logging.info(f"Config file {config_file} unchanged")
            return False

        backup_index = 1
        backup_file = f"{config_file}.freeipa_mailcow_bak"
        while os.path.exists(backup_file):
            backup_file = f"{config_file}.freeipa_mailcow_bak.{backup_index}"
            backup_index += 1

        os.rename(config_file, backup_file)
        logging.info(f"Backed up {config_file} to {backup_file}")

    Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)

    print(config_data, file=open(config_file, 'w'))
    
    logging.info(f"Saved generated config file to {config_file}")
    return True

def read_config():
    required_config_keys = [
        'FREEIPA_MAILCOW_LDAP_URI', 
        'FREEIPA_MAILCOW_LDAP_BASE_DN',
        'FREEIPA_MAILCOW_LDAP_BIND_DN', 
        'FREEIPA_MAILCOW_LDAP_BIND_DN_PASSWORD',
        'FREEIPA_MAILCOW_MAIL_DOMAIN',
        'FREEIPA_MAILCOW_API_HOST', 
        'FREEIPA_MAILCOW_API_KEY', 
        'FREEIPA_MAILCOW_SYNC_INTERVAL'
    ]

    config = {}
    filter_groups = []
    domain_to_group = {}

    if 'COMPOSE_PROJECT_NAME' in os.environ:
        config['COMPOSE_PROJECT_NAME']=os.environ['COMPOSE_PROJECT_NAME']
    else:
        config['COMPOSE_PROJECT_NAME']='mailcowdockerized'

    for config_key in required_config_keys:
        if config_key not in os.environ:
            sys.exit (f"Required environment value {config_key} is not set")

        config[config_key.replace('FREEIPA_MAILCOW_', '')] = os.environ[config_key]

    if 'FREEIPA_MAILCOW_LDAP_FILTER_GROUP' in os.environ:
        grpval = os.environ['FREEIPA_MAILCOW_LDAP_FILTER_GROUP']
        filter_groups.append(grpval)
    else:
        grpval = ''
    domain_to_group[ config['MAIL_DOMAIN'] ] = grpval

    mdPattern = re.compile(r'FREEIPA_MAILCOW_MAIL_DOMAIN_(\d*)')
    for domkey, domval in os.environ.items():
        mdMatch = mdPattern.match(domkey)
        if mdMatch:
            grpkey = 'FREEIPA_MAILCOW_LDAP_FILTER_GROUP_' + mdMatch.group(1)
            if grpkey in os.environ:
                grpval = os.environ[grpkey]
                filter_groups.append(grpval)
            else:
                grpval = ''
            domain_to_group[domval] = grpval

    config['MAIL_DOMAIN'] = domain_to_group

    if len(filter_groups) == 1:
        config['LDAP_FILTER'] = '(&(objectclass=inetorgperson)(memberOf=cn=' \
            + filter_groups[0] \
            + ',cn=groups,cn=accounts,' \
            + config['LDAP_BASE_DN'] \
            + '))'
        config['SOGO_LDAP_FILTER'] = "objectClass='inetorgperson' AND memberOf='cn=" \
            + filter_groups[0] \
            + ",cn=groups,cn=accounts," \
            + config['LDAP_BASE_DN'] \
            + "'"
    elif len(filter_groups) > 1:
        fullgrp = mkfullgroup(filter_groups[0])
        config['LDAP_FILTER'] = '(memberOf=' + fullgrp + ')'
        config['SOGO_LDAP_FILTER'] = "memberOf='" + fullgrp + "'"
        filter_groups.pop(0)
        for filter_group in filter_groups:
            fullgrp = mkfullgroup(filter_group)
            config['LDAP_FILTER'] = '(|' + config['LDAP_FILTER'] + '(memberOf=' + fullgrp + '))'
            config['SOGO_LDAP_FILTER'] = config['SOGO_LDAP_FILTER'] + " OR memberOf='" + fullgrp + "'"
        config['LDAP_FILTER'] = '(&(objectclass=inetorgperson)' + config['LDAP_FILTER'] + ')'
        config['SOGO_LDAP_FILTER'] = "objectClass='inetorgperson' AND (" + config['SOGO_LDAP_FILTER'] + ")"
    else:
        config['LDAP_FILTER'] = '(objectclass=inetorgperson)'
        config['SOGO_LDAP_FILTER'] = "objectClass='inetorgperson'"

    return config

def read_dovecot_passdb_conf_template():
    with open('templates/dovecot/ldap/passdb.conf') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_uri=config['LDAP_URI'], 
        ldap_base_dn=config['LDAP_BASE_DN']
        )

def read_sogo_plist_ldap_template():
    with open('templates/sogo/plist_ldap') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_uri=config['LDAP_URI'],
        ldap_port='636',
        ldap_enc='SSL',
        ldap_base_dn=config['LDAP_BASE_DN'],
        ldap_bind_dn=config['LDAP_BIND_DN'],
        ldap_bind_dn_password=config['LDAP_BIND_DN_PASSWORD'],
        sogo_ldap_filter=config['SOGO_LDAP_FILTER']
        )

def read_dovecot_extra_conf():
    with open('templates/dovecot/extra.conf') as f:
        data = f.read()

    return data

if __name__ == '__main__':
    main()
