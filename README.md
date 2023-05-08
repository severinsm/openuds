![UDS Logo](https://www.udsenterprise.com/static//img/logoUDSNav.png)

openuds
=======

OpenUDS (Universal Desktop Services) is a multiplatform connection broker for:
- VDI: Windows and Linux virtual desktops administration and deployment
- App virtualization
- Desktop services consolidation

This is an Open Source Source project, initiated by Spanish Company ​Virtualcable and released Open Source with the help of several Spanish Universities.

Any help provided will be welcome.

**Note: Master version is always under heavy development and it is not recommended for use, it will probably have unfixed bugs.  Please use the latest stable branch.**

____________________________

_____________________

## **I'm working to dockerize this application, and make some personal small improvements**

### **points of notice**

default credentials.\
root:uds

you can adjust the default credentials in:
server\src\uds\core\util\config.php

default is ssl redirect enabled, so then you need to set this behind a reverse proxy.
you can turn it off by modifying 2 files (the server\src\server\settings.py & server\src\uds\core\util\config.py)

- **set redirectToHttps to 0;**
```


     # Redirect HTTP to HTTPS
    REDIRECT_TO_HTTPS: Config.Value = Config.section(GLOBAL_SECTION).value(
        'redirectToHttps', '0', type=Config.BOOLEAN_FIELD
    )
```

- **comment this out**

```
SECURE_PROXY_SSL_HEADER = (
    'HTTP_X_FORWARDED_PROTO',
    'https',
)  
```

### don't forget to run taskManager

taskManager is the background process that does the work for you, default it's not started. If you don't enable this, the Virtual machines will not be created for you, nor actions will be completed in UDS. (like cleanup etc.)
you can start it with: 
```
python manage.py taskManager --start &
```


## before using UDS, you need to create the database tables etc. ##

- fill in server\src\server\settings.py
- run the migrate function to let UDS create the database structure:
```
python manage.py migrate
```

### **todo list**

- fix requirements
- make django 4 compatible
- compile actors
- compile clients
- convert UDS to docker images
- create docker compose for the full stack (db, server, tunnel+proxy & guacamole)
- get deployment going with terraform
- deploy in k8 cluster
- setup CI/CD for deployment
- setup CI/CD for build & released
