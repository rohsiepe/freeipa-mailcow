# freeipa-mailcow

Adds LDAP accounts to mailcow-dockerized and enables LDAP authentication with a FreeIPA backend.

## Currently, this doesn't work at all. Turn to the original, programmierus/ldap-mailcow, for something working

* [How does it work](#how-does-it-work)
* [Usage](#usage)
  * [LDAP Fine-tuning](#ldap-fine-tuning)
* [Limitations](#limitations)
  * [WebUI and EAS authentication](#webui-and-eas-authentication)
  * [Two-way sync](#two-way-sync)
* [Customizations and Integration support](#customizations-and-integration-support)

## How does it work

A python script periodically checks and creates new LDAP accounts and deactivates deleted and disabled ones with mailcow API. It also enables LDAP authentication in SOGo and dovecot.

## Usage

0. On your FreeIPA host, herein called ipa.example.local, create a system user for mailcow.

```bash
    # ldapmodify -x -D 'cn=Directory Manager' -W
    dn: uid=mailcow,cn=sysaccounts,cn=etc,dc=example,dc=local
    changetype: add
    objectclass: account
    objectclass: simplesecurityobject
    uid: system
    userPassword: secret123
    passwordExpirationTime: 20380119031407Z
    nsIdleTimeout: 0
    <blank line>
    ^D
```

1. **Optional** Using the FreeIPA gui, create a group for all your mail users (e.g. mailusers)
2. We assume, your mailcow lives in opt/mailcow-dockerized. Check out this software side by side:

```bash
    # cd /opt
    # git clone https://github.com/rohsiepe/freeipa-mailcow
    ^D
```

3. Inside the mailcow-dockerized installation folder, create a `data/ldap` directory. SQLite database for synchronization will be stored there.
4. Extend your `docker-compose.override.yml` with an additional container:

    ```yaml
    freeipa-mailcow:
      image: rohsiepe/freeipa-mailcow
      build: ../freeipa-mailcow/
      volumes:
        - ./data/ldap:/db:rw
        - ./data/conf/dovecot:/conf/dovecot:rw
        - ./data/conf/sogo:/conf/sogo:rw
      depends_on:
        - nginx-mailcow
      environment:
        - FREEIPA_MAILCOW_LDAP_URI=ldaps://ipa.example.local
        - FREEIPA_MAILCOW_LDAP_BASE_DN=dc=example,dc=local
        - FREEIPA_MAILCOW_LDAP_BIND_DN=uid=mailcow,cn=sysaccounts,cn=etc,dc=example,dc=local
        - FREEIPA_MAILCOW_LDAP_BIND_DN_PASSWORD=secret123
        - FREEIPA_MAILCOW_API_HOST=https://mailcow.example.local
        - FREEIPA_MAILCOW_API_KEY=XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
        - FREEIPA_MAILCOW_SYNC_INTERVAL=300
        - FREEIPA_MAILCOW_MAIL_DOMAIN=example.local
        - FREEIPA_MAILCOW_LDAP_FILTER_GROUP=mailusers
        - COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-mailcowdockerized}
      restart: always
      networks:
        mailcow-network:

    ```

5. Configure environmental variables:

    * `FREEIPA_MAILCOW_LDAP_URI` - LDAP URI (must be reachable from within the container). The URIs are in syntax `protocol://host:port`. For example `ldap://localhost` or `ldaps://secure.domain.org`
    * `FREEIPA_MAILCOW_LDAP_BASE_DN` - base DN where user accounts can be found
    * `FREEIPA_MAILCOW_LDAP_BIND_DN` - bind DN of a special LDAP account that will be used to browse for users, cf. step 0
    * `FREEIPA_MAILCOW_LDAP_BIND_DN_PASSWORD` - password for bind DN account
    * `FREEIPA_MAILCOW_API_HOST` - mailcow API url. Make sure it's enabled and accessible from within the container for both reads and writes
    * `FREEIPA_MAILCOW_API_KEY` - mailcow API key (read/write)
    * `FREEIPA_MAILCOW_SYNC_INTERVAL` - interval in seconds between LDAP synchronizations
    * `FREEIPA_MAILCOW_MAIL_DOMAIN` - users are registered with Mailcow with an email address in this domain
    * **Optional** `FREEIPA_MAILCOW_LDAP_FILTER_GROUP` - LDAP filter group, users must be members of this group in order to be registered
    * **Optional** `FREEIPA_MAILCOW_MAIL_DOMAIN_2` - another mail domain
    * **Optional** `FREEIPA_MAILCOW_LDAP_FILTER_GROUP_2` - filter for above

    You can define as many mail domains and filter groups as you like.

4. Start additional container: `docker compose up -d freeipa-mailcow`
5. Check logs `docker compose logs freeipa-mailcow`

### LDAP Fine-tuning

Container internally uses the following configuration templates:

* SOGo: `/templates/sogo/plist_ldap`
* dovecot: `/templates/dovecot/ldap/passdb.conf`

These files have been tested against a small hobbyist FreeIPA installation. If need be, they can of course be modified. Some documentation on these files can be found here: [dovecot](https://doc.dovecot.org/configuration_manual/authentication/ldap/), [SOGo](https://sogo.nu/files/docs/SOGoInstallationGuide.html#_authentication_using_ldap)

## Limitations

### WebUI and EAS authentication

This tool enables authentication for Dovecot and SOGo, which means you will be able to log into POP3, SMTP, IMAP, and SOGo Web-Interface. **You will not be able to log into mailcow UI or EAS using your LDAP credentials by default.**

As a workaround, you can hook IMAP authentication directly to mailcow by adding the following code above [this line](https://github.com/mailcow/mailcow-dockerized/blob/48b74d77a0c39bcb3399ce6603e1ad424f01fc3e/data/web/inc/functions.inc.php#L608):

```php
    $mbox = imap_open ("{dovecot:993/imap/ssl/novalidate-cert}INBOX", $user, $pass);
    if ($mbox != false) {
        imap_close($mbox);
        return "user";
    }
```

As a side-effect, It will also allow logging into mailcow UI using mailcow app passwords (since they are valid for IMAP). **It is not a supported solution with mailcow and has to be done only at your own risk!**

### Two-way sync

Users from your LDAP directory will be added (and deactivated if disabled/not found) to your mailcow database. Not vice-versa, and this is by design.

## Customizations and Integration support

This fork is specifically targeted at FreeIPA installations using a single mail domain. If you want AD integration or custom modifications, you are propably better off using the original programmierus/ldap-mailcow. Programmierus also offers paid support and/or custom modifications. 
