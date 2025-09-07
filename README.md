# DevOps Starter Repo — Terraform • Packer • Ansible • CI/CD • Notebook

Production‑ready starter kit to build a **Golden AMI**, provision infra with **Terraform**, configure with **Ansible**, and automate via **GitHub Actions / Jenkins**. Includes a Jupyter Notebook for hands‑on YAML/JSON + AWS automation.

---

## Repository Layout

```
devops-starter-repo/
├── ansible/
│   ├── site.yml                 # Example playbook (installs Nginx)
│   └── aws_inventory.py         # Exports EC2 → inventory (YAML)
├── terraform/
│   ├── main.tf                  # VPC, subnet, EC2 (uses var.ami_id)
│   ├── variables.tf
│   └── outputs.tf
├── packer/
│   └── packer.json              # Golden AMI (Docker + Nginx)
├── .github/workflows/
│   └── deploy.yml               # GitHub Actions pipeline (TF + Ansible)
├── Jenkinsfile                  # Declarative pipeline (TF + Packer + Ansible)
└── notebook.ipynb               # DevOps practice notebook
```

> **Heads‑up:** `terraform/main.tf` requires an `ami_id`. You can either **build it with Packer** (recommended) or **use a public Ubuntu AMI** for testing.

---

## Prerequisites

- AWS account + IAM user/role with permissions:
  - **Packer**: `ec2:DescribeImages`, `ec2:RegisterImage`, `ec2:CreateTags`, `iam:PassRole` (if using instance profile)
  - **Terraform**: standard VPC/EC2 create/read/update/delete
- Local CLIs: `git`, `terraform (>= 1.5)`, `packer (>= 1.9)`, `python3`, `pip`, `ansible`
- Python libs (for inventory): `pip install boto3 pyyaml`
- AWS credentials set via **environment** or **AWS CLI**:
  ```bash
  export AWS_ACCESS_KEY_ID=... 
  export AWS_SECRET_ACCESS_KEY=...
  export AWS_DEFAULT_REGION=eu-west-2
  # or: aws configure
  ```

---

## 1) Build a Golden AMI with Packer (Docker + Nginx)

`packer/packer.json` builds an Ubuntu‑based AMI with Docker and a running Nginx container.

```bash
cd packer
packer build packer.json
```

Grab the **AMI ID** from the build output (or from EC2 → AMIs).  
_Optional (recommended):_ add a manifest post‑processor so the AMI ID is saved to `packer/manifest.json`:

```json
"post-processors": [
  { "type": "manifest", "output": "packer/manifest.json" }
]
```

Then you can read it later:
```bash
jq -r '.builds[-1].artifact_id' packer/manifest.json  # e.g. "amazon-ebs:ami-0123456789abcdef0"
```

---

## 2) Provide the AMI to Terraform

Create `terraform/terraform.tfvars`:

```hcl
ami_id = "ami-0123456789abcdef0"
```

---

## 3) Provision Infrastructure with Terraform

```bash
cd terraform
terraform init
terraform apply -auto-approve   # uses terraform.tfvars
```

Outputs include the created instance ID.

> **Note:** The sample TF creates a VPC, a public subnet, and one EC2 instance using your AMI.

---

## 4) Configure Hosts with Ansible

From repo root (so the inventory writes to the root as referenced by pipelines):

```bash
pip install boto3 pyyaml ansible

# Generate inventory from running EC2 instances in eu-west-2
python ansible/aws_inventory.py

# Inspect the generated file
cat aws_inventory.yml

# Run the example playbook (installs nginx via apt)
ansible-playbook -i aws_inventory.yml ansible/site.yml
```

### Inventory format note
If Ansible warns about inventory structure, replace `ansible/aws_inventory.py` with this safer mapping version:

```python
import boto3, yaml
ec2 = boto3.client('ec2', region_name='eu-west-2')
resp = ec2.describe_instances()
inv = {'all': {'hosts': {}}}
for r in resp['Reservations']:
    for i in r['Instances']:
        if i['State']['Name'] == 'running' and 'PublicIpAddress' in i:
            ip = i['PublicIpAddress']
            inv['all']['hosts'][ip] = {'ansible_host': ip, 'ansible_user': 'ubuntu'}
with open('aws_inventory.yml', 'w') as f:
    yaml.dump(inv, f)
```

---

## 5) GitHub Actions CI/CD

### Add Secrets
In **Repo Settings → Secrets and variables → Actions → New repository secret**, add:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` = `eu-west-2`
- `TF_VAR_ami_id` = your AMI ID (or commit `terraform.tfvars` as shown above)

### Fix the default workflow (runs in correct directories)
Edit `.github/workflows/deploy.yml` to run Terraform inside `/terraform` and use your AMI var:

```yaml
name: Deploy Infra + Config

on:
  push:
    branches: [ "main" ]

env:
  AWS_DEFAULT_REGION: ${{ secrets.AWS_DEFAULT_REGION }}
  TF_VAR_ami_id: ${{ secrets.TF_VAR_ami_id }}

jobs:
  infra:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.6.6
      - name: Terraform Init
        working-directory: terraform
        run: terraform init
      - name: Terraform Apply
        working-directory: terraform
        run: terraform apply -auto-approve

  config:
    runs-on: ubuntu-latest
    needs: infra
    steps:
      - uses: actions/checkout@v3
      - name: Install deps
        run: pip install boto3 ansible pyyaml
      - name: Generate AWS Inventory
        run: python ansible/aws_inventory.py
      - name: Run Ansible
        run: ansible-playbook -i aws_inventory.yml ansible/site.yml
```

#### (Optional) Build AMI in Actions
If you want Actions to **build the AMI** too, add a job:

```yaml
  ami:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: hashicorp/setup-packer@v2
      - name: Build AMI
        run: |
          packer build packer/packer.json | tee packer_output.txt
          # parse AMI id and expose as output (adjust grep/awk as needed)
          echo "AMI_ID=$(grep -Eo 'ami-[0-9a-f]+' packer_output.txt | tail -1)" >> $GITHUB_ENV
    outputs:
      AMI_ID: ${{ env.AMI_ID }}

  infra:
    needs: ami
    # ... then set TF_VAR_ami_id to needs.ami.outputs.AMI_ID
```

---

## 6) Jenkins Pipeline

The provided `Jenkinsfile` is a starting point. **Recommended order** is: **build AMI → Terraform apply → Ansible**. Update your `Jenkinsfile` like this:

```groovy
pipeline {
  agent any
  environment {
    AWS_DEFAULT_REGION = 'eu-west-2'
  }
  stages {
    stage('Build Golden AMI') {
      steps {
        sh '''
          packer build packer/packer.json | tee packer_output.txt
          AMI_ID=$(grep -Eo 'ami-[0-9a-f]+' packer_output.txt | tail -1)
          echo AMI_ID=$AMI_ID > ami.env
        '''
        script {
          def props = readProperties file: 'ami.env'
          env.TF_VAR_ami_id = props['AMI_ID']
        }
      }
    }
    stage('Terraform Init & Apply') {
      steps {
        dir('terraform') {
          sh 'terraform init'
          sh 'terraform apply -auto-approve'
        }
      }
    }
    stage('Deploy with Ansible') {
      steps {
        sh 'pip install boto3 pyyaml ansible'
        sh 'python ansible/aws_inventory.py'
        sh 'ansible-playbook -i aws_inventory.yml ansible/site.yml'
      }
    }
  }
}
```

> If you prefer a robust AMI ID capture, add a **manifest** post‑processor in `packer.json` and read it with `jq` rather than grepping logs.

---

## 7) Cleanup

```bash
cd terraform
terraform destroy -auto-approve
```

Also deregister test AMIs and delete snapshots if you’re done testing.

---

## 8) Troubleshooting

- **Terraform asks for `ami_id`** → create `terraform/terraform.tfvars` or set `TF_VAR_ami_id`.
- **Packer fails with permissions** → ensure IAM user/role allows EC2 image actions.
- **Ansible inventory error** → use the “mapping” version of `aws_inventory.py` above.
- **No public IP** → ensure subnet is public and/or add an internet gateway/NAT and appropriate route tables.
- **GitHub Actions fails in Terraform step** → ensure steps run with `working-directory: terraform` and secrets are set.

---

## 9) Roadmap Ideas

- Add **security groups** and **IGW/route tables** to Terraform.
- Use **Ansible roles** (nginx hardening, app deploy).
- Convert `packer.json` to **HCL** and add **manifest** + **ansible** provisioners.
- Add **dynamic inventory plugin** or **AWS EC2 inventory** for Ansible.
- Integrate **Snyk/Trivy** scans in CI/CD.

---

Happy shipping! 🚀
