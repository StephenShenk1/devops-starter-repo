import boto3, yaml

ec2 = boto3.client('ec2', region_name='eu-west-2')
instances = ec2.describe_instances()

inventory = {'all': {'hosts': []}}
for res in instances['Reservations']:
    for inst in res['Instances']:
        if inst['State']['Name'] == 'running':
            inventory['all']['hosts'].append(inst['PublicIpAddress'])

with open('aws_inventory.yml', 'w') as f:
    yaml.dump(inventory, f)
