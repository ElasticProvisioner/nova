Using WSGI with Nova
====================

Since the version 2025.2 the only way to run the compute API and metadata API
is using a generic HTTP server that supports WSGI_ (such as Apache_ or nginx_).

The nova project provides two automatically generated entry points that
support this: ``nova-api-wsgi`` and ``nova-metadata-wsgi``. These read
``nova.conf`` and ``api-paste.ini`` by default and generate the required
module-level ``application`` that most WSGI servers require.
If nova is installed using pip, these two scripts will be installed into
whatever the expected ``bin`` directory is for the environment.

The config files and config directory can be overridden via the
``OS_NOVA_CONFIG_FILES`` and ``OS_NOVA_CONFIG_DIR`` environment variables.
File paths listed in ``OS_NOVA_CONFIG_FILES`` are relative to
``OS_NOVA_CONFIG_DIR`` and delimited by ``;``.


The new scripts replace older experimental scripts that could be found in the
``nova/wsgi`` directory of the code repository. The new scripts are *not*
experimental.

When running the compute and metadata services with WSGI, sharing the compute
and metadata service in the same process is not supported (as it is in the
eventlet-based scripts).

In devstack as of May 2017, the compute and metadata APIs are hosted by a
Apache communicating with uwsgi_ via mod_proxy_uwsgi_. Inspecting the
configuration created there can provide some guidance on one option for
managing the WSGI scripts. It is important to remember, however, that one of
the major features of using WSGI is that there are many different ways to host
a WSGI application. Different servers make different choices about performance
and configurability.

.. _WSGI: https://www.python.org/dev/peps/pep-3333/
.. _apache: http://httpd.apache.org/
.. _nginx: http://nginx.org/en/
.. _uwsgi: https://uwsgi-docs.readthedocs.io/
.. _mod_proxy_uwsgi: http://uwsgi-docs.readthedocs.io/en/latest/Apache.html#mod-proxy-uwsgi
