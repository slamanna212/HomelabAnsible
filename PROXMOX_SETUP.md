# Proxmox Dynamic Inventory Setup Guide

## Prerequisites

### 1. Python Dependencies

The Proxmox inventory plugin requires the following Python libraries on the **control server**:

```bash
sudo apt update
sudo apt install -y python3-requests python3-proxmoxer
```

Or using pip:
```bash
pip3 install requests proxmoxer
```

**Required libraries:**
- `requests` (>= 1.1) - HTTP library for API communication
- `proxmoxer` - Proxmox API wrapper library (recommended but may work without it)

### 2. Ansible Collection

The `community.proxmox` collection must be installed:

```bash
ansible-galaxy collection install -r collections/requirements.yml --force
```

**Note:** The `--force` flag ensures the collection is reinstalled even if it exists.

## Semaphore Configuration

### Environment Variables

Configure these environment variables in Semaphore (create a "Proxmox Inventory" variable group):

| Variable Name | Type | Secret | Example Value | Description |
|---------------|------|--------|---------------|-------------|
| PROXMOX_URL | Environment | No | https://10.90.90.x:8006 | Proxmox API endpoint |
| PROXMOX_USER | Environment | No | ansible@pam | Proxmox username (user@realm format) |
| PROXMOX_TOKEN_ID | Environment | Yes | ansible@pam!semaphore | Token ID (format: user@realm!tokenname) |
| PROXMOX_TOKEN_SECRET | Environment | Yes | xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx | Token secret value |

**Important:** The `PROXMOX_USER` should match the username portion of `PROXMOX_TOKEN_ID`.
- If `PROXMOX_TOKEN_ID` is `ansible@pam!semaphore`
- Then `PROXMOX_USER` should be `ansible@pam`

### Creating Proxmox API Token

1. Log into Proxmox web UI
2. Navigate to **Datacenter → Permissions → API Tokens**
3. Click **Add**
4. Configure:
   - **User:** Select user (e.g., `ansible@pam`)
   - **Token ID:** `semaphore` (or any identifier)
   - **Privilege Separation:** Unchecked (token inherits user permissions)
5. Click **Add**
6. **IMPORTANT:** Copy the token secret immediately (only shown once)
7. Note the full Token ID format: `user@realm!tokenname` (e.g., `ansible@pam!semaphore`)

### Required Permissions

The user associated with the token needs at least:
- **VM.Audit** - Read access to VM configuration
- **Sys.Audit** - Read access to node information

**Recommended:** Assign the built-in **PVEAuditor** role for read-only access to everything.

## Proxmox VM Tagging

VMs must be tagged in Proxmox to be assigned to Ansible groups. Each tag becomes a group name.

### Required Tags

Tag VMs in Proxmox with these group names:

| Tag | Purpose | Example VMs |
|-----|---------|-------------|
| control | Ansible/Semaphore control server | ansible-control |
| loadbalancers | HAProxy load balancers | haproxy-01 |
| web | Nginx web servers | web-01, web-02 |
| wp-admin | WordPress admin servers | wpadmin-01 |
| nfs-server | NFS shared storage | nfs-01 |
| database | MariaDB database servers | db-01 |
| tunnel | Cloudflare tunnel servers | cftunnel-01 |
| zabbix-server | Zabbix monitoring | zabbix-01 |
| bluesky | Bluesky PDS | bluesky-01 |
| radio | AzuraCast radio | radio-01 |
| docker | Docker hosts | docker-01 |
| logging | Log aggregation | logs-01 |

### How to Tag VMs in Proxmox

1. Select a VM in Proxmox UI
2. Go to VM **Options** or **Summary**
3. Find the **Tags** field
4. Add tags (comma-separated for multiple tags)
5. Click **OK** to save

**Example:** A VM can have multiple tags like `web,monitoring` to appear in both groups.

## Testing the Inventory

### Test Commands

```bash
# View inventory structure
ansible-inventory -i inventory.proxmox.yml --graph

# View detailed inventory (JSON)
ansible-inventory -i inventory.proxmox.yml --list

# View specific group
ansible-inventory -i inventory.proxmox.yml --graph web

# Test connectivity to all hosts
ansible -i inventory.proxmox.yml all -m ping

# Test connectivity to specific group
ansible -i inventory.proxmox.yml web -m ping
```

### Run Test Playbook

```bash
ansible-playbook test_proxmox_inventory.yml
```

This playbook will:
- Display all discovered groups
- Show host details (hostname, IP, groups)
- Test critical inventory patterns
- Test connectivity to all hosts

## Troubleshooting

### "Failed to load inventory plugin"

**Causes:**
- Inventory file doesn't match required naming pattern
- Wrong plugin name used in configuration

**Solutions:**
- Inventory file must be named `*.proxmox.yml` or `*.proxmox.yaml` (e.g., `inventory.proxmox.yml`)
- Plugin name must be `community.proxmox.proxmox` (NOT `community.proxmox.proxmox_inventory`)
- The old `community.general.proxmox_inventory` plugin is deprecated

### "No module named 'requests'" or "No module named 'proxmoxer'"

**Cause:** Missing Python dependencies.

**Solution:** Install on control server:
```bash
sudo apt install -y python3-requests python3-proxmoxer
```

### "Failed to connect to Proxmox API"

**Causes:**
- PROXMOX_URL is incorrect or inaccessible
- Firewall blocking port 8006
- SSL certificate issues

**Solutions:**
- Verify URL: `curl -k https://<proxmox-ip>:8006`
- Check firewall allows port 8006
- Ensure `validate_certs: false` in inventory.proxmox.yml for self-signed certs

### "Authentication failed" or "No setting was provided for required configuration setting: user"

**Causes:**
- Missing PROXMOX_USER environment variable
- Token ID format incorrect
- Token secret wrong
- Token expired or deleted
- Insufficient permissions
- User and token ID mismatch

**Solutions:**
- Ensure PROXMOX_USER environment variable is set (e.g., `ansible@pam`)
- Verify PROXMOX_USER matches the username portion of PROXMOX_TOKEN_ID
- Verify token ID format: `user@realm!tokenname`
- Regenerate token in Proxmox if needed
- Check user has PVEAuditor role

### "No hosts found" or "Empty inventory"

**Causes:**
- VMs not running
- VMs missing network configuration
- Environment variables not set
- No VMs match filters

**Solutions:**
- Verify VMs are running in Proxmox
- Check VMs have IP addresses
- Verify environment variables in Semaphore
- Use `-vvv` flag for debug output:
  ```bash
  ansible-inventory -i inventory.proxmox.yml --list -vvv
  ```

### "Group not found" in playbooks

**Cause:** VM tags in Proxmox don't match required group names.

**Solution:** Either:
- Update VM tags in Proxmox to match required names
- Add group mappings to inventory.proxmox.yml:
  ```yaml
  groups:
    web: "'webserver' in proxmox_tags_parsed"
    database: "'db' in proxmox_tags_parsed"
  ```

### Semaphore Skips Collection Install

**Cause:** Semaphore caches collections/requirements.yml and skips if unchanged.

**Solution:**
- Modify the requirements.yml file (add a comment or change version)
- Or manually install on control server:
  ```bash
  ansible-galaxy collection install community.proxmox --force
  ```

### Control Server Shows Wrong IP

**Cause:** Proxmox reports the VM's actual IP, but playbooks expect 127.0.0.1

**Solution:** Create `host_vars/<control-hostname>.yml`:
```yaml
ansible_host: 127.0.0.1
```

## Inventory File Details

The inventory file (`inventory.proxmox.yml`) configuration:

- **Plugin:** `community.proxmox.proxmox`
- **Authentication:** Via environment variables (PROXMOX_URL, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET)
- **SSL Validation:** Disabled for self-signed certs (`validate_certs: false`)
- **IP Selection:** Uses first IPv4 address from VM
- **Grouping:** Creates groups based on VM tags
- **Meta-group:** All VMs added to `ubuntu` group
- **Caching:** Enabled for 30 minutes (configured in ansible.cfg)

## Performance Optimization

### Inventory Caching

Caching is enabled in `ansible.cfg` to reduce API calls:

```ini
[inventory]
cache = yes
cache_plugin = jsonfile
cache_timeout = 1800
cache_connection = /tmp/ansible_inventory_cache
```

**To clear cache:**
```bash
rm -rf /tmp/ansible_inventory_cache
```

**Note:** Clear cache after adding/removing VMs or changing tags.

## Migration from Static Inventory

Once the test playbook succeeds:

1. Test existing playbooks with dynamic inventory:
   ```bash
   ansible-playbook -i inventory.proxmox.yml site.yml --check
   ```

2. Update Semaphore task templates to use dynamic inventory

3. Preserve `ExampleInventory` as reference (rename to `ExampleInventory.reference`)

4. Update documentation to reflect dynamic inventory usage
