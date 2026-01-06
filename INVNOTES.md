
 Critical Existing Files (for reference, not modified):
 - /home/slamanna212/Git/HomelabAnsible/roles/haproxy/templates/haproxy.cfg - Uses hostvars[host].ansible_host pattern (line 68, 83)
 - /home/slamanna212/Git/HomelabAnsible/site.yml - Uses groups['web'] and groups['wp-admin'] pattern (line 46-47)
 - /home/slamanna212/Git/HomelabAnsible/roles/nfs-client/tasks/main.yml - Uses groups['nfs-server'][0] pattern
