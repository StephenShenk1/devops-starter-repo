pipeline {
    agent any
    stages {
        stage('Terraform Init & Apply') {
            steps {
                sh 'terraform init'
                sh 'terraform apply -auto-approve'
            }
        }
        stage('Build Golden AMI with Packer') {
            steps {
                sh 'packer build packer/packer.json'
            }
        }
        stage('Deploy with Ansible') {
            steps {
                sh 'python ansible/aws_inventory.py'
                sh 'ansible-playbook -i aws_inventory.yml ansible/site.yml'
            }
        }
    }
}
