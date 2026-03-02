# Kubernetes Cluster Ansible Playbooks — Full Implementation Plan
 
## Context
The homelab is expanding to include a production-grade HA Kubernetes cluster managed through
the existing Ansible/Semaphore setup. This plan covers everything from OS baseline to a running
cluster with ArgoCD ready for GitOps app deployments.
 
**Cluster hardware:**
- 3x control plane nodes (4 vCPU / 4GB RAM / 30GB NVMe) — Proxmox tags: `k8control`, `k8s`, `os_debian`
- 4x worker nodes (12-16 vCPU / 8-32GB RAM / 100GB NVMe OS disk + 150GB SATA SSD) — Proxmox tags: `k8work`, `k8s`, `os_debian`
 
**Software stack:** Debian 13 / containerd / kubeadm / kube-vip (HA VIP) / Cilium / MetalLB /
Traefik / Longhorn (2-tier: NVMe + SATA) / Helm / ArgoCD
 
Ansible bootstraps the cluster end-to-end. ArgoCD takes over for all app deployments
(Prometheus, Grafana, Loki, etc.) after bootstrap completes.
 
---
 
## Prerequisites — Proxmox VM Tags
 
Each K8s VM needs these Proxmox tags set before running the playbook.
The dynamic inventory (community.proxmox.proxmox) auto-creates groups from tags.
 
| VM | Required Tags |
|---|---|
| Slama-Read-K8Ctrl01/02/03 | `k8control` `k8s` `os_debian` |
| Slama-Read-K8Work01/02/03/04 | `k8work` `k8s` `os_debian` |
 
- `k8s` → combined group targeting all 7 nodes in one play
- `k8control` / `k8work` → role-specific targeting
- `os_debian` → picked up by `site.yml` for ongoing weekly maintenance (no changes to site.yml needed)
 
**IMPORTANT — Kubernetes hostname requirement:** Kubernetes node names must be lowercase
RFC-1123 compliant. The existing Proxmox VM names ("Slama-Read-K8Ctrl01") are mixed case.
The `k8s-common` role will set the hostname to lowercase as part of setup. Ensure VM names
only contain letters, digits, and hyphens (they already do).
 
---
 
## Semaphore Variable Groups to Create
 
Create these 4 variable groups in Semaphore UI and attach them to the K8s task template:
 
**k8s-cluster:**
```
k8s_vip               = <VIP IP address, e.g. 10.90.90.10>
k8s_vip_interface     = eth0
k8s_version           = 1.31
k8s_pod_cidr          = 10.244.0.0/16
k8s_service_cidr      = 10.96.0.0/12
kube_vip_version      = v0.8.9
```
 
**k8s-storage:**
```
longhorn_sata_disk    = sdb
```
(Override per-host in host_vars/ if workers have different device names — see Implementation Notes)
 
**k8s-networking:**
```
metallb_ip_pool       = <IP range, e.g. 10.90.90.200-10.90.90.250>
```
 
**k8s-monitoring:**
```
K8sClusterHC          = https://hc-ping.com/<your-hash>
```
 
---
 
## Complete File List
 
```
# NEW files
roles/k8s-common/tasks/main.yml
roles/k8s-common/vars/main.yml
roles/k8s-common/handlers/main.yml
roles/k8s-common/templates/kube-vip.yaml.j2
roles/k8s-longhorn-prep/tasks/main.yml
K8sLifecycle/NewK8sCluster.yml
K8sUtility/K8sNodeDrain.yml
group_vars/k8s.yml
group_vars/k8control.yml
group_vars/k8work.yml
 
# MODIFIED files
extra_vars_TEMPLATE.yml    (append K8s variable block)
```
 
---
 
## File: `group_vars/k8s.yml`
```yaml
---
ansible_python_interpreter: /usr/bin/python3
 
# Extra packages installed by the debian base role on all K8s nodes
add_packages:
  - curl
  - wget
  - apt-transport-https
  - ca-certificates
  - gnupg
  - lsb-release
  - net-tools
  - htop
```
 
## File: `group_vars/k8control.yml`
```yaml
---
ansible_python_interpreter: /usr/bin/python3
```
 
## File: `group_vars/k8work.yml`
```yaml
---
ansible_python_interpreter: /usr/bin/python3
```
 
---
 
## File: `roles/k8s-common/vars/main.yml`
```yaml
---
k8s_packages:
  - "kubelet"
  - "kubeadm"
  - "kubectl"
 
containerd_packages:
  - containerd.io
```
 
## File: `roles/k8s-common/handlers/main.yml`
```yaml
---
- name: restart containerd
  ansible.builtin.service:
    name: containerd
    state: restarted
 
- name: apply sysctl
  ansible.builtin.command: sysctl --system
  changed_when: false
```
 
## File: `roles/k8s-common/templates/kube-vip.yaml.j2`
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kube-vip
  namespace: kube-system
spec:
  containers:
  - args:
    - manager
    env:
    - name: vip_arp
      value: "true"
    - name: PORT
      value: "6443"
    - name: vip_interface
      value: {{ k8s_vip_interface }}
    - name: vip_cidr
      value: "32"
    - name: cp_enable
      value: "true"
    - name: cp_namespace
      value: kube-system
    - name: vip_ddns
      value: "false"
    - name: svc_enable
      value: "true"
    - name: vip_leaderelection
      value: "true"
    - name: vip_leaseduration
      value: "5"
    - name: vip_renewdeadline
      value: "3"
    - name: vip_retryperiod
      value: "1"
    - name: address
      value: {{ k8s_vip }}
    image: ghcr.io/kube-vip/kube-vip:{{ kube_vip_version }}
    imagePullPolicy: Always
    name: kube-vip
    securityContext:
      capabilities:
        add:
        - NET_ADMIN
        - NET_RAW
    volumeMounts:
    - mountPath: /etc/kubernetes/admin.conf
      name: kubeconfig
  hostAliases:
  - hostnames:
    - kubernetes
    ip: 127.0.0.1
  hostNetwork: true
  volumes:
  - hostPath:
      path: /etc/kubernetes/admin.conf
    name: kubeconfig
```
 
## File: `roles/k8s-common/tasks/main.yml`
 
Full task list — every task in order:
 
```yaml
---
# ===== Hostname (Kubernetes requires lowercase RFC-1123) =====
- name: Set hostname to lowercase
  ansible.builtin.hostname:
    name: "{{ inventory_hostname | lower }}"
    use: systemd
 
# ===== Swap =====
- name: Disable swap immediately
  ansible.builtin.command: swapoff -a
  changed_when: false
 
- name: Remove swap entries from fstab
  ansible.builtin.replace:
    path: /etc/fstab
    regexp: '^([^#].*\sswap\s.*)$'
    replace: '# \1'
 
# ===== Kernel modules =====
- name: Load kernel modules at boot
  ansible.builtin.copy:
    dest: /etc/modules-load.d/k8s.conf
    content: |
      overlay
      br_netfilter
    mode: '0644'
 
- name: Load overlay module now
  community.general.modprobe:
    name: overlay
    state: present
 
- name: Load br_netfilter module now
  community.general.modprobe:
    name: br_netfilter
    state: present
 
# ===== Sysctl =====
- name: Configure sysctl for Kubernetes networking
  ansible.builtin.copy:
    dest: /etc/sysctl.d/k8s.conf
    content: |
      net.bridge.bridge-nf-call-iptables  = 1
      net.bridge.bridge-nf-call-ip6tables = 1
      net.ipv4.ip_forward                 = 1
    mode: '0644'
  notify: apply sysctl
 
# ===== containerd =====
- name: Install GPG package
  ansible.builtin.apt:
    name: gpg
    state: present
    update_cache: no
 
- name: Download Docker GPG key for containerd repo
  ansible.builtin.shell: |
    curl -fsSL https://download.docker.com/linux/debian/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod 644 /etc/apt/keyrings/docker.gpg
  args:
    creates: /etc/apt/keyrings/docker.gpg
 
- name: Add Docker apt repository (for containerd.io)
  ansible.builtin.apt_repository:
    repo: "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable"
    filename: docker
    state: present
 
- name: Install containerd
  ansible.builtin.apt:
    name: containerd.io
    state: present
    update_cache: yes
  notify: restart containerd
 
- name: Create containerd config directory
  ansible.builtin.file:
    path: /etc/containerd
    state: directory
    mode: '0755'
 
- name: Generate default containerd config
  ansible.builtin.shell: containerd config default > /etc/containerd/config.toml
  args:
    creates: /etc/containerd/config.toml
  notify: restart containerd
 
- name: Enable SystemdCgroup in containerd config
  ansible.builtin.replace:
    path: /etc/containerd/config.toml
    regexp: 'SystemdCgroup = false'
    replace: 'SystemdCgroup = true'
  notify: restart containerd
 
- name: Set pause image in containerd config
  ansible.builtin.replace:
    path: /etc/containerd/config.toml
    regexp: 'sandbox_image = ".*"'
    replace: 'sandbox_image = "registry.k8s.io/pause:3.10"'
  notify: restart containerd
 
- name: Enable and start containerd
  ansible.builtin.service:
    name: containerd
    state: started
    enabled: yes
 
# ===== Kubernetes packages =====
- name: Create Kubernetes apt keyring directory
  ansible.builtin.file:
    path: /etc/apt/keyrings
    state: directory
    mode: '0755'
 
- name: Download Kubernetes GPG key
  ansible.builtin.shell: |
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v{{ k8s_version }}/deb/Release.key | \
    gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg
  args:
    creates: /etc/apt/keyrings/kubernetes-apt-keyring.gpg
 
- name: Add Kubernetes apt repository
  ansible.builtin.apt_repository:
    repo: "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v{{ k8s_version }}/deb/ /"
    filename: kubernetes
    state: present
 
- name: Install Kubernetes packages
  ansible.builtin.apt:
    name: "{{ k8s_packages }}"
    state: present
    update_cache: yes
 
- name: Hold Kubernetes packages at installed version
  ansible.builtin.dpkg_selections:
    name: "{{ item }}"
    selection: hold
  loop:
    - kubelet
    - kubeadm
    - kubectl
 
- name: Enable and start kubelet
  ansible.builtin.service:
    name: kubelet
    state: started
    enabled: yes
 
# ===== Helm =====
- name: Check if Helm is already installed
  ansible.builtin.stat:
    path: /usr/local/bin/helm
  register: helm_binary
 
- name: Install Helm
  ansible.builtin.shell: |
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  when: not helm_binary.stat.exists
```
 
---
 
## File: `roles/k8s-longhorn-prep/tasks/main.yml`
 
```yaml
---
# ===== Longhorn prerequisites =====
- name: Install Longhorn prerequisites
  ansible.builtin.apt:
    name:
      - open-iscsi
      - nfs-common
      - jq
      - cryptsetup
      - dmsetup
    state: present
    update_cache: yes
 
- name: Enable and start iscsid
  ansible.builtin.service:
    name: iscsid
    state: started
    enabled: yes
 
# ===== NVMe tier (uses existing OS disk free space) =====
- name: Create Longhorn NVMe data directory
  ansible.builtin.file:
    path: /var/lib/longhorn
    state: directory
    mode: '0750'
 
# ===== SATA tier (separate 150GB SATA SSD) =====
# longhorn_sata_disk defaults to 'sdb' — override per-host in host_vars/ if needed
- name: Check if SATA disk is already formatted
  ansible.builtin.shell: blkid /dev/{{ longhorn_sata_disk }}
  register: sata_blkid
  changed_when: false
  failed_when: false
 
- name: Format SATA disk as XFS
  ansible.builtin.shell: mkfs.xfs /dev/{{ longhorn_sata_disk }}
  when: sata_blkid.rc != 0
 
- name: Create Longhorn SATA mount point
  ansible.builtin.file:
    path: /var/lib/longhorn-sata
    state: directory
    mode: '0750'
 
- name: Get SATA disk UUID
  ansible.builtin.shell: blkid -s UUID -o value /dev/{{ longhorn_sata_disk }}
  register: sata_uuid
  changed_when: false
 
- name: Mount SATA disk and persist in fstab
  ansible.posix.mount:
    path: /var/lib/longhorn-sata
    src: "UUID={{ sata_uuid.stdout | trim }}"
    fstype: xfs
    opts: defaults
    dump: '0'
    passno: '2'
    state: mounted
```
 
---
 
## File: `K8sLifecycle/NewK8sCluster.yml`
 
```yaml
---
# =============================================================================
# NewK8sCluster.yml
# Bootstraps a full HA Kubernetes cluster from bare Debian 13 OS.
# Run once to create the cluster. Safe to re-run — all steps are idempotent.
#
# Required Semaphore variable groups: k8s-cluster, k8s-storage,
#                                     k8s-networking, k8s-monitoring
#
# Node hardware:
#   Control: 3x nodes (4c/4GB/30GB NVMe) — Proxmox tags: k8control, k8s, os_debian
#   Workers: 4x nodes (8-16c/8-32GB/100GB NVMe + 150GB SATA) — Proxmox tags: k8work, k8s, os_debian
#     Work01: 12c/32GB  Work02: 12c/32GB  Work03: 8c/8GB*  Work04: 16c/32GB
#     * Work03 is below Longhorn's recommended 4GB RAM minimum — monitor storage carefully
# =============================================================================
 
- name: Start of Job Monitoring
  hosts: localhost
  tasks:
    - name: Tell Healthchecks.io that we started the playbook
      ansible.builtin.uri:
        url: "{{ K8sClusterHC }}/start"
        timeout: 10
        force: true
 
# -----------------------------------------------------------------------------
# Play 1: Baseline all K8s nodes — OS config + containerd + k8s packages + Helm
# Uses the 'k8s' Proxmox tag group (all 7 nodes: 3 control + 4 workers)
# -----------------------------------------------------------------------------
- name: Prepare all Kubernetes nodes
  hosts: k8s
  become: true
  roles:
    - debian
    - k8s-common
    - zabbix-agent
    - wazuh-agent
 
# -----------------------------------------------------------------------------
# Play 2: Longhorn storage prep on workers — format SATA disk, install prereqs
# -----------------------------------------------------------------------------
- name: Prepare worker nodes for Longhorn storage
  hosts: k8work
  become: true
  roles:
    - k8s-longhorn-prep
 
# -----------------------------------------------------------------------------
# Play 3: Initialize the first control plane node
# - Places kube-vip static pod manifest (for HA VIP)
# - Runs kubeadm init
# - Captures join commands and passes them to later plays via dummy host
# -----------------------------------------------------------------------------
- name: Initialize first control plane node
  hosts: k8control[0]
  become: true
  tasks:
    - name: Check if cluster is already initialized
      ansible.builtin.stat:
        path: /etc/kubernetes/admin.conf
      register: admin_conf
 
    - name: Create manifests directory (needed before kubeadm init)
      ansible.builtin.file:
        path: /etc/kubernetes/manifests
        state: directory
        mode: '0755'
 
    - name: Template kube-vip static pod manifest
      ansible.builtin.template:
        src: "{{ playbook_dir }}/../roles/k8s-common/templates/kube-vip.yaml.j2"
        dest: /etc/kubernetes/manifests/kube-vip.yaml
        mode: '0644'
 
    - name: Initialize Kubernetes cluster
      ansible.builtin.shell: >
        kubeadm init
        --control-plane-endpoint "{{ k8s_vip }}:6443"
        --upload-certs
        --pod-network-cidr {{ k8s_pod_cidr }}
        --service-cidr {{ k8s_service_cidr }}
      when: not admin_conf.stat.exists
      register: kubeadm_init
 
    - name: Apply kube-vip RBAC (required for leader election)
      ansible.builtin.shell: kubectl apply -f https://kube-vip.io/manifests/rbac.yaml
      environment:
        KUBECONFIG: /etc/kubernetes/admin.conf
      when: not admin_conf.stat.exists
      changed_when: true
 
    - name: Set up kubeconfig for ansible user
      ansible.builtin.file:
        path: /home/ansible/.kube
        state: directory
        owner: ansible
        group: ansible
        mode: '0755'
 
    - name: Copy admin.conf for ansible user
      ansible.builtin.copy:
        src: /etc/kubernetes/admin.conf
        dest: /home/ansible/.kube/config
        remote_src: yes
        owner: ansible
        group: ansible
        mode: '0600'
 
    - name: Re-upload certs and capture certificate key
      ansible.builtin.shell: kubeadm init phase upload-certs --upload-certs 2>&1 | tail -1
      register: cert_key_result
      changed_when: false
 
    - name: Generate control plane join command
      ansible.builtin.shell: >
        kubeadm token create
        --print-join-command
        --certificate-key {{ cert_key_result.stdout | trim }}
      register: control_join_result
      changed_when: false
 
    - name: Generate worker join command
      ansible.builtin.shell: kubeadm token create --print-join-command
      register: worker_join_result
      changed_when: false
 
    - name: Store join commands for use in later plays
      ansible.builtin.add_host:
        name: K8S_JOIN_DATA
        control_join_command: "{{ control_join_result.stdout }}"
        worker_join_command: "{{ worker_join_result.stdout }}"
 
# -----------------------------------------------------------------------------
# Play 4: Join the remaining control plane nodes (ctrl02 and ctrl03)
# kube-vip must be placed before joining so it participates in leader election
# -----------------------------------------------------------------------------
- name: Join additional control plane nodes
  hosts: k8control[1:]
  become: true
  tasks:
    - name: Check if node is already joined
      ansible.builtin.stat:
        path: /etc/kubernetes/kubelet.conf
      register: kubelet_conf
 
    - name: Create manifests directory
      ansible.builtin.file:
        path: /etc/kubernetes/manifests
        state: directory
        mode: '0755'
 
    - name: Template kube-vip static pod manifest
      ansible.builtin.template:
        src: "{{ playbook_dir }}/../roles/k8s-common/templates/kube-vip.yaml.j2"
        dest: /etc/kubernetes/manifests/kube-vip.yaml
        mode: '0644'
 
    - name: Join as control plane node
      ansible.builtin.shell: "{{ hostvars['K8S_JOIN_DATA']['control_join_command'] }}"
      when: not kubelet_conf.stat.exists
 
# -----------------------------------------------------------------------------
# Play 5: Join worker nodes
# -----------------------------------------------------------------------------
- name: Join worker nodes
  hosts: k8work
  become: true
  tasks:
    - name: Check if node is already joined
      ansible.builtin.stat:
        path: /etc/kubernetes/kubelet.conf
      register: kubelet_conf
 
    - name: Join as worker node
      ansible.builtin.shell: "{{ hostvars['K8S_JOIN_DATA']['worker_join_command'] }}"
      when: not kubelet_conf.stat.exists
 
# -----------------------------------------------------------------------------
# Play 6: Deploy cluster applications via Helm (runs from ctrl01 as ansible user)
# Order matters: CNI first (nodes become Ready), then load balancer, ingress,
# storage, then GitOps.
# All helm upgrade --install calls are idempotent — safe to re-run.
# -----------------------------------------------------------------------------
- name: Deploy cluster applications
  hosts: k8control[0]
  become: true
  environment:
    KUBECONFIG: /etc/kubernetes/admin.conf
  tasks:
 
    # --- Wait for nodes ---
    - name: Wait for all nodes to be Ready
      ansible.builtin.shell: kubectl wait --for=condition=Ready nodes --all --timeout=300s
      changed_when: false
 
    # --- Cilium CNI ---
    - name: Add Cilium Helm repo
      ansible.builtin.shell: helm repo add cilium https://helm.cilium.io/
      changed_when: false
 
    - name: Deploy Cilium CNI
      ansible.builtin.shell: >
        helm upgrade --install cilium cilium/cilium
        --namespace kube-system
        --set kubeProxyReplacement=true
        --set k8sServiceHost={{ k8s_vip }}
        --set k8sServicePort=6443
        --wait --timeout 5m
      register: cilium_deploy
      changed_when: "'already up-to-date' not in cilium_deploy.stdout"
 
    # --- MetalLB ---
    - name: Add MetalLB Helm repo
      ansible.builtin.shell: helm repo add metallb https://metallb.github.io/metallb
      changed_when: false
 
    - name: Deploy MetalLB
      ansible.builtin.shell: >
        helm upgrade --install metallb metallb/metallb
        --namespace metallb-system
        --create-namespace
        --wait --timeout 5m
      register: metallb_deploy
      changed_when: "'already up-to-date' not in metallb_deploy.stdout"
 
    - name: Wait for MetalLB webhook to be ready
      ansible.builtin.shell: >
        kubectl wait --namespace metallb-system
        --for=condition=ready pod
        --selector=app=metallb
        --timeout=90s
      changed_when: false
 
    - name: Configure MetalLB IP address pool
      ansible.builtin.shell: |
        kubectl apply -f - <<EOF
        apiVersion: metallb.io/v1beta1
        kind: IPAddressPool
        metadata:
          name: homelab-pool
          namespace: metallb-system
        spec:
          addresses:
          - {{ metallb_ip_pool }}
        ---
        apiVersion: metallb.io/v1beta1
        kind: L2Advertisement
        metadata:
          name: homelab-l2
          namespace: metallb-system
        spec:
          ipAddressPools:
          - homelab-pool
        EOF
      changed_when: true
 
    # --- Traefik Ingress ---
    - name: Add Traefik Helm repo
      ansible.builtin.shell: helm repo add traefik https://traefik.github.io/charts
      changed_when: false
 
    - name: Deploy Traefik ingress controller
      ansible.builtin.shell: >
        helm upgrade --install traefik traefik/traefik
        --namespace traefik
        --create-namespace
        --wait --timeout 5m
      register: traefik_deploy
      changed_when: "'already up-to-date' not in traefik_deploy.stdout"
 
    # --- Longhorn Storage ---
    - name: Add Longhorn Helm repo
      ansible.builtin.shell: helm repo add longhorn https://charts.longhorn.io
      changed_when: false
 
    - name: Deploy Longhorn
      ansible.builtin.shell: >
        helm upgrade --install longhorn longhorn/longhorn
        --namespace longhorn-system
        --create-namespace
        --set defaultSettings.defaultDataPath=/var/lib/longhorn
        --wait --timeout 10m
      register: longhorn_deploy
      changed_when: "'already up-to-date' not in longhorn_deploy.stdout"
 
    - name: Wait for Longhorn Node objects to be created
      ansible.builtin.shell: >
        kubectl -n longhorn-system get node.longhorn.io
        --no-headers | wc -l
      register: longhorn_nodes
      until: longhorn_nodes.stdout | int >= groups['k8work'] | length
      retries: 20
      delay: 15
      changed_when: false
 
    - name: Add SATA disk to each worker node in Longhorn
      ansible.builtin.shell: |
        kubectl -n longhorn-system patch node.longhorn.io {{ item | lower }} \
          --type=merge \
          --patch '{
            "spec": {
              "disks": {
                "longhorn-sata": {
                  "path": "/var/lib/longhorn-sata",
                  "allowScheduling": true,
                  "storageReserved": 10737418240,
                  "tags": ["sata"]
                }
              }
            }
          }'
      loop: "{{ groups['k8work'] }}"
      register: longhorn_patch
      changed_when: longhorn_patch.rc == 0
      failed_when: longhorn_patch.rc != 0
 
    - name: Create Longhorn NVMe StorageClass (default)
      ansible.builtin.shell: |
        kubectl apply -f - <<EOF
        kind: StorageClass
        apiVersion: storage.k8s.io/v1
        metadata:
          name: longhorn-nvme
          annotations:
            storageclass.kubernetes.io/is-default-class: "true"
        provisioner: driver.longhorn.io
        allowVolumeExpansion: true
        parameters:
          numberOfReplicas: "2"
          diskSelector: "nvme"
          dataLocality: "disabled"
        EOF
      changed_when: true
 
    - name: Create Longhorn SATA StorageClass
      ansible.builtin.shell: |
        kubectl apply -f - <<EOF
        kind: StorageClass
        apiVersion: storage.k8s.io/v1
        metadata:
          name: longhorn-sata
        provisioner: driver.longhorn.io
        allowVolumeExpansion: true
        parameters:
          numberOfReplicas: "2"
          diskSelector: "sata"
          dataLocality: "disabled"
        EOF
      changed_when: true
 
    # --- ArgoCD ---
    - name: Add ArgoCD Helm repo
      ansible.builtin.shell: helm repo add argo https://argoproj.github.io/argo-helm
      changed_when: false
 
    - name: Deploy ArgoCD
      ansible.builtin.shell: >
        helm upgrade --install argocd argo/argo-cd
        --namespace argocd
        --create-namespace
        --wait --timeout 10m
      register: argocd_deploy
      changed_when: "'already up-to-date' not in argocd_deploy.stdout"
 
    - name: Get ArgoCD initial admin password
      ansible.builtin.shell: >
        kubectl -n argocd get secret argocd-initial-admin-secret
        -o jsonpath='{.data.password}' | base64 -d
      register: argocd_password
      changed_when: false
 
    - name: Display ArgoCD admin password
      ansible.builtin.debug:
        msg: "ArgoCD admin password: {{ argocd_password.stdout }}"
 
- name: End of Job Monitoring
  hosts: localhost
  tasks:
    - name: Tell Healthchecks.io that we finished the playbook
      ansible.builtin.uri:
        url: "{{ K8sClusterHC }}"
        timeout: 10
        force: true
```
 
---
 
## File: `K8sUtility/K8sNodeDrain.yml`
 
```yaml
---
# Safely drain a Kubernetes node before maintenance.
# Run this before rebooting or removing a node.
# After maintenance, the node will re-join automatically when kubelet restarts.
 
- name: Drain Kubernetes node
  hosts: k8control[0]
  become: true
  environment:
    KUBECONFIG: /etc/kubernetes/admin.conf
  vars_prompt:
    - name: node_name
      prompt: "Enter the node name to drain (run 'kubectl get nodes' to see names)"
      private: no
 
  tasks:
    - name: Cordon node (mark as unschedulable)
      ansible.builtin.shell: kubectl cordon {{ node_name | lower }}
      changed_when: true
 
    - name: Drain node
      ansible.builtin.shell: >
        kubectl drain {{ node_name | lower }}
        --ignore-daemonsets
        --delete-emptydir-data
        --grace-period=60
      changed_when: true
 
    - name: Show node status after drain
      ansible.builtin.shell: kubectl get node {{ node_name | lower }}
      register: node_status
      changed_when: false
 
    - name: Display node status
      ansible.builtin.debug:
        msg: "{{ node_status.stdout }}\n\nNode is drained. After maintenance, uncordon with:\nkubectl uncordon {{ node_name | lower }}"
```
 
---
 
## Additions to `extra_vars_TEMPLATE.yml`
 
Append to the existing file:
 
```yaml
# Kubernetes Cluster
K8sClusterHC: https://hc-ping.com/[replace-with-hash]
k8s_vip: ""                    # Control plane virtual IP (e.g. 10.90.90.10)
k8s_vip_interface: "eth0"      # Network interface name on K8s nodes for kube-vip
k8s_version: "1.31"            # Kubernetes version minor (e.g. 1.31)
k8s_pod_cidr: "10.244.0.0/16"  # Pod network CIDR (Cilium default)
k8s_service_cidr: "10.96.0.0/12"
kube_vip_version: "v0.8.9"
metallb_ip_pool: ""            # IP range for LoadBalancer services (e.g. 10.90.90.200-10.90.90.250)
longhorn_sata_disk: "sdb"      # SATA block device on workers (override in host_vars/ if differs per node)
```
 
---
 
## Implementation Notes
 
**Per-node SATA disk override:**
If different workers have different SATA device names, create host_vars files:
```
host_vars/slama-read-k8work03.yml   → longhorn_sata_disk: sdc
```
Host variables override group variables — this is the cleanest way to handle per-node differences.
 
**Longhorn disk tags:**
The NVMe tier uses the default Longhorn path `/var/lib/longhorn` (no tag selector needed for the default StorageClass). The SATA tier is tagged `sata` and targeted by the `longhorn-sata` StorageClass. Worker03 (8GB RAM) may show warnings in Longhorn — this is expected.
 
**Join command timing:**
Join tokens expire after 24 hours by default. If re-running the playbook on already-joined nodes, the join tasks are skipped via the `stat /etc/kubernetes/kubelet.conf` check. If you need to re-join a node that was reset, run `kubeadm reset` on the node first.
 
**kube-vip leader election:**
kube-vip uses the Kubernetes lease API for leader election. The `hostAlias` entry (`kubernetes: 127.0.0.1`) in the static pod manifest allows kube-vip to bootstrap before the cluster API is fully available on the VIP. This is the standard kube-vip static pod pattern.
 
**ArgoCD follow-up:**
After bootstrap, configure ArgoCD to manage app deployments (Prometheus, Grafana, Loki) by creating an Application manifest in your Git repo and adding the repo to ArgoCD. Ansible's job ends once ArgoCD is running.
 
**site.yml:**
No changes needed. K8s nodes tagged `os_debian` will be included in the weekly `site.yml` run for OS package upgrades and monitoring agent updates. The `debian` and monitoring roles are idempotent and safe to re-apply.
 
---
 
## Verification Steps (in order)
 
1. **After Play 1** — SSH to any K8s node: `containerd --version`, `kubeadm version`, `helm version`
2. **After Play 2** — SSH to any worker: `lsblk` shows SATA mounted at `/var/lib/longhorn-sata`
3. **After Play 3** — On ctrl01: `kubectl get nodes` → 1 node, status `NotReady` (no CNI yet)
4. **After Play 4** — On ctrl01: `kubectl get nodes` → 3 control plane nodes, all `NotReady`
5. **After Play 5** — On ctrl01: `kubectl get nodes` → all 7 nodes visible
6. **After Cilium** — `kubectl get nodes` → all nodes become `Ready`; `kubectl -n kube-system get pods -l k8s-app=cilium` → all Running
7. **After MetalLB** — `kubectl get ipaddresspools -n metallb-system` → `homelab-pool` present
8. **After Traefik** — `kubectl get pods -n traefik` → Running; `kubectl get svc -n traefik` → EXTERNAL-IP assigned from MetalLB pool
9. **After Longhorn** — `kubectl get pods -n longhorn-system` → all Running; access Longhorn UI via `kubectl port-forward -n longhorn-system svc/longhorn-frontend 8080:80`; verify each worker shows 2 disks (NVMe + SATA)
10. **After ArgoCD** — `kubectl get pods -n argocd` → all Running; log in at ArgoCD UI with printed password (user: `admin`)
11. **Idempotency check** — Re-run full playbook → all tasks should report `ok`, none `changed` (except healthchecks.io pings and `changed_when: true` markers)
12. **HA test** — Power off ctrl01, verify `kubectl get nodes` still works via kube-vip VIP from ctrl02 or ctrl03