This folder holds the config files and specs to create a production ready KIND cluster that insludes:

- Kubernetes Gateway API routing and load balancing
- IP provisioning
- automated certificate management through cert manager
    - one shared wildcard cert for *.undpgeohub.org
- oauth2-proxy authentication based on Github
-demo apps
    - simple demo app 
    - oauth2 based demoapp

The result is a KIND cluster ready for hosting apps.