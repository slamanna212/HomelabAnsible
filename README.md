![Wordpress Updater](https://healthchecks.io/b/2/3d61fb8a-e25b-437b-991e-b17e1b298906.svg) ![Site Playbook](https://healthchecks.io/b/2/f29511d4-f1d7-4477-8ad4-6ef7b1328f87.svg)

# Homelab Ansible Playbooks
Ansible playbooks for a web hosting cluster running on local vSphere server. 

# Initial Setup

## Cloudflare
Cloudflare is heavily used. A tunnel is used to route all traffic and a Cloudflare Origin cert is used on the loadbalancer. 

## Assumptions
Currently these playbooks assume a couple things, this is being worked on and this list will be reduced eventually.

 - An ansible user with passwordless sudo and public key auth needs to already exist. I use [Cubic](https://github.com/PJ-Singh-001/Cubic) to include this in the initial unintended install of ubuntu.
 - All VMs use DHCP and a network of 10.90.90.0/24
 - All VMs are Ubuntu 24
 - Cloudflare tunnels are setup manually currently.
 - Zabbix templates and Autodiscover actions need to be configured manually.
 - A non public vault password is currently needed.

# Initial Setup

1. Create a server for Ansible to run on. [Install ansible.](https://docs.ansible.com/ansible/latest/installation_guide/installation_distros.html#installing-ansible-on-ubuntu) 
2. Clone this repo. Create a hosts file at `/etc/ansible/hosts` with just the database group
3. Run the initial playbook. `ansible-playbook init-site.yml --ask-vault-pass`
4. Run the `NewDatabase.yml` playbook to create a database for Semaphore
5. Install [Semaphore](https://github.com/semaphoreui/semaphore/releases)
6. Setup Sempaphore by running `semaphore setup`
7. Run Semaphore `semaphore server --config=/etc/semaphore/config.json` , You can use screen or a startup manager to make this start automatically.
8. Go to `http://ip-of-ansible-server:3000` in a web browser. 
9. Setup your inventory using the example in this repo (`ExampleInventory`)
10. Setup your Variable Group using `extra_vars_TEMPLATE.yml` as an example.
11. Setup this or your fork of this repository under Repositories.
12. Setup your playbooks under Task Templates
13. Run `site.yml` to deploy entire cluster
14. Create new sites on the cluster with `NewWordpressSite.yml`


# Playbooks
 - `site.yml` - Entire Cluster. *Meant to be run on a schedule/cron. Weekly*

## *Lifecycle
 - `NewDatabase.yml` - Creates a database, allows the rest of the cluster to talk to it. 
 - `NewWordpressSite.yml` - Creates a new wordpress website on the cluster. 

## *Utility
 - `ClearNginxCache.yml` - Clears the FastCGI cache for a website. Useful to run this after making big changes to a site.
 - `ReloadWeb.yml` - Reloads the configuration for all of the Web and WPAdmin servers. Run after making nginx config changes. 
 - `WordpressUpdater.yml` - Updates all Plugins, all Themes, and the core Wordpress version for all WordPress sites on the cluster. *Meant to be run on a schedule/cron. Daily*