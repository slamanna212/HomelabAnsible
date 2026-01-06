# Proxmox Homelab Ansible Repository


## Purpose

Ansible playbooks for managing an entire home network infrastructure running on Proxmox. Originally created for a WordPress hosting cluster, now expanding to manage the entire home network.

## Execution Environment

- **Primary Interface**: All playbooks are run exclusively through **Semaphore UI**
- **Automation**:
  - `WordpressUpdater.yml` runs nightly
  - `site.yml` runs weekly
  - Other playbooks run as needed
- **Security**: All files are safe to read/modify - this is a public repository with no secrets

## Architecture Overview

### Current WordPress Cluster (10.90.90.0/24 network)

**Web Tier**:
- Nginx web servers (read-only WordPress serving)
- WP-Admin servers (WordPress admin interface, cron jobs)
- HAProxy load balancer with Cloudflare Origin certificates

**Data Tier**:
- MariaDB database
- NFS server for shared WordPress file storage

**Infrastructure**:
- Cloudflare tunnel for external routing
- Zabbix monitoring with healthchecks.io integration
- Control server running Ansible/Semaphore

**Additional Services**:
- Bluesky PDS
- AzuraCast radio server
- Docker host
- Logging server

### Expansion Scope

The repository is expanding to manage the entire home network across multiple networks. The 10.90.90.0/24 network is the WordPress cluster network, but Semaphore can reach all networks as needed.

## Repository Structure

### Main Playbooks

- **`site.yml`**: Full cluster deployment (runs weekly via cron)
- **`init-site.yml`**: Initial cluster setup

### Lifecycle Playbooks (`*Lifecycle/`)

- `NewDatabase.yml`: Create database and configure cluster access
- `NewWordpressSite.yml`: Deploy new WordPress site
- `NewBarebonesWordpress.yml`: Minimal WordPress deployment

### Utility Playbooks (`*Utility/`)

- `WordpressUpdater.yml`: Update all WP plugins, themes, and core (runs nightly)
- `ClearNginxCache.yml`: Clear FastCGI cache after major site changes
- `ReloadWeb.yml`: Reload nginx config on web/wp-admin servers

### Roles

- `ubuntu`: Base Ubuntu 24 configuration
- `nginx`: Web server configuration
- `wp-admin`: WordPress admin server setup
- `wp-cron`: WordPress cron management
- `haproxy`: Load balancer configuration
- `mariadb`: Database server setup
- `nfs-server`: NFS server configuration
- `nfs-client`: NFS client mount configuration
- `zabbix-agent`: Monitoring agent installation
- `control`: Control server configuration

### Host Groups

- `[control]`: Ansible/Semaphore server
- `[loadbalancers]`: HAProxy servers
- `[web]`: Read-only nginx WordPress servers
- `[wp-admin]`: WordPress admin servers
- `[nfs-server]`: Shared storage server
- `[database]`: MariaDB servers
- `[tunnel]`: Cloudflare tunnel servers
- `[zabbix-server]`: Monitoring server
- `[logging]`: Log aggregation server
- `[bluesky]`: Bluesky PDS server
- `[radio]`: AzuraCast server
- `[docker]`: Docker host
- `[ubuntu]`: All Ubuntu servers

## Environment Assumptions

From `README.md` - these assumptions are being reduced over time:

- Ansible user with passwordless sudo and public key auth pre-configured (using Cubic for Ubuntu ISOs)
- All VMs currently use DHCP on their respective networks
- All VMs are Ubuntu 24
- Cloudflare tunnels configured manually (for now)
- Zabbix templates and autodiscovery actions configured manually
- Ansible Vault password required for encrypted variables

## Networking

- **WordPress Cluster**: 10.90.90.0/24
- **Additional Networks**: TBD - playbooks will specify network context
- **External Access**: Via Cloudflare tunnels

## Next Priority Tasks

1. **Proxmox Dynamic Inventory**: Implement Proxmox API integration for dynamic inventory generation
2. **Network Expansion**: Extend playbooks to manage full home network
3. **Automation**: Reduce manual configuration steps (Cloudflare tunnels, Zabbix)

## Integration Notes

- Uses Ansible Vault for sensitive variables
- Healthchecks.io monitoring for playbook execution
- Semaphore provides UI, scheduling, and logging
- Inventory file location: `/etc/ansible/hosts` on control server
- Variable groups configured in Semaphore UI

## Development Notes

- Repository is publicly accessible
- All changes tested in production (homelab environment)
- Focus on idempotency and repeatability
