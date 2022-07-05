from unicodedata import name
import pulumi
import pulumi_azure as azure
import pulumi_azure_native as az
from pulumi_azure_native import storage
from pulumi_azure_native import compute
from pulumi_azure_native import network
from pulumi_azure_native import resources
from pulumi import Config, Output, export
import base64
from operator import truediv

# Create an Azure Resource Group
resource_group = resources.ResourceGroup(
    'StaticWebSiteRG', resource_group_name="StaticWebSiteRG")

# Create an Azure resource (Storage Account)
account = storage.StorageAccount('sa',
                                 resource_group_name=resource_group.name,
                                 sku=storage.SkuArgs(
                                     name=storage.SkuName.STANDARD_LRS,
                                 ),
                                 kind=storage.Kind.STORAGE_V2)

# Export the primary key of the Storage Account
primary_key = pulumi.Output.all(resource_group.name, account.name) \
    .apply(lambda args: storage.list_storage_account_keys(
        resource_group_name=args[0],
        account_name=args[1]
    )).apply(lambda accountKeys: accountKeys.keys[0].value)

static_website = storage.StorageAccountStaticWebsite('StaticWebsite',
                                                     account_name=account.name,
                                                     resource_group_name=resource_group.name,
                                                     index_document='index.html')

# Upload the file
index_html = storage.Blob("index.html",
                          resource_group_name=resource_group.name,
                          account_name=account.name,
                          container_name=static_website.container_name,
                          source=pulumi.FileAsset("index.html"),
                          content_type="text/html")

pulumi.export("primary_storage_key", primary_key)
# Web endpoint to the website
pulumi.export("staticEndpoint", account.primary_endpoints.web)

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Load Balanced Server Part \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

config = Config()
username = config.require("username")
password = config.require("password")

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Resource Group Number 2 \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
resource_group2 = resources.ResourceGroup(
    "Server_RG", resource_group_name='Server_RG')

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Virtual Network and LB roules\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
net = network.VirtualNetwork(
    resource_name = "server-network",
    virtual_network_name="server-network",
    resource_group_name=resource_group2.name,
    address_space=network.AddressSpaceArgs(
        address_prefixes=["10.0.0.0/16"],
    ),
    subnets=[network.SubnetArgs(
        name="default",
        address_prefix="10.0.1.0/24",
    )])

public_ip = az.network.PublicIPAddress("publicIPAddress",
    idle_timeout_in_minutes=10,
    location= resource_group2.location,
    public_ip_address_version="IPv4",
    public_ip_allocation_method="Static",
    public_ip_address_name="test-ip",
    resource_group_name= resource_group2.name,
    sku=az.network.PublicIPAddressSkuArgs(
        name="Standard",
        tier="Regional",
    ))

load_balancer = azure.lb.LoadBalancer(
    resource_name= "exampleLoadBalancer",
    name="exampleLoadBalancer",
    location= resource_group2.location,
    resource_group_name= resource_group2.name,
    sku= "Standard",
    frontend_ip_configurations=[azure.lb.LoadBalancerFrontendIpConfigurationArgs(
        name="PublicIPAddress",
        public_ip_address_id= public_ip.id,
    )])
backend_address_pool = azure.lb.BackendAddressPool(name = "bckaddpool", resource_name="bckaddpool", loadbalancer_id= load_balancer.id)

rule = azure.lb.Rule(
    name = "RulePort22",
    resource_name= "RulePort22",
    loadbalancer_id= load_balancer.id,
    protocol="Tcp",
    frontend_port= 22,
    backend_port= 22,
    frontend_ip_configuration_name = "PublicIPAddress",
    backend_address_pool_ids = [backend_address_pool.id],
    )
rule2 = azure.lb.Rule(
    name = "RulePort80",
    resource_name= "RulePort80",
    loadbalancer_id= load_balancer.id,
    protocol="Tcp",
    frontend_port= 80,
    backend_port= 80,
    frontend_ip_configuration_name = "PublicIPAddress",
    backend_address_pool_ids = [backend_address_pool.id],
    )
rule3 = azure.lb.Rule(
    name = "RulePort445",
    resource_name= "RulePort445",
    loadbalancer_id= load_balancer.id,
    protocol="Tcp",
    frontend_port= 445,
    backend_port= 445,
    frontend_ip_configuration_name = "PublicIPAddress",
    backend_address_pool_ids = [backend_address_pool.id],
    )

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Load Balanced Server Part \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
i = 0
while i < 2:
    i += 1
    
    network_iface = network.NetworkInterface(
        resource_name=f"server-nic{i}",
        network_interface_name=f"server-nic{i}",
        resource_group_name=resource_group2.name,
        ip_configurations=[network.NetworkInterfaceIPConfigurationArgs(
            name=f"webserveripcfg{i}",
            subnet=network.SubnetArgs(id=net.subnets[0].id),
            private_ip_allocation_method=network.IPAllocationMethod.DYNAMIC,
            # public_ip_address=network.PublicIPAddressArgs(id=public_ip.id),
        )])
     
    network_interface_backend_address_pool_association = azure.network.NetworkInterfaceBackendAddressPoolAssociation(
    resource_name = f"BackendAddressPoolAssociation{i}",
    network_interface_id= network_iface.id,
    ip_configuration_name= f"webserveripcfg{i}",
    backend_address_pool_id= backend_address_pool.id),

    init_script = """#!/bin/bash
    echo "Hello, World!" > index.html
    nohup python -m SimpleHTTPServer 80 &"""

    vm = compute.VirtualMachine(
        resource_name=f"server-vm{i}",
        vm_name= f"server-vm{i}",
        resource_group_name=resource_group2.name,
        network_profile=compute.NetworkProfileArgs(
            network_interfaces=[
                compute.NetworkInterfaceReferenceArgs(id=network_iface.id),
            ],
        ),
        hardware_profile=compute.HardwareProfileArgs(
            vm_size=compute.VirtualMachineSizeTypes.STANDARD_B2S,
        ),
        os_profile=compute.OSProfileArgs(
            computer_name=f"hostname{i}",
            admin_username=username,
            admin_password=password,
            custom_data=base64.b64encode(
                init_script.encode("ascii")).decode("ascii"),
            linux_configuration=compute.LinuxConfigurationArgs(
                disable_password_authentication=False,
            ),
        ),
        storage_profile=compute.StorageProfileArgs(
            os_disk=compute.OSDiskArgs(
                create_option=compute.DiskCreateOptionTypes.FROM_IMAGE,
                name=f"myosdisk{i}",
            ),
            image_reference=compute.ImageReferenceArgs(
                publisher="canonical",
                offer="UbuntuServer",
                sku="16.04-LTS",
                version="latest",
            ),
        ))


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ NSG Part \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

network_security_group = azure.network.NetworkSecurityGroup(resource_name= "NetworkSecurityGroup",
    name="NetworkSecurityGroup",
    location= resource_group2.location,
    resource_group_name= resource_group2.name,)

NetworkSR2 = azure.network.NetworkSecurityRule(
        resource_name="NSGRules",
        name= "NSGRules",
        priority=100,
        direction="Inbound",
        access="Allow",
        protocol="Tcp",
        source_port_range= "*",
        destination_port_ranges=["22","80","445"],
        source_address_prefix="*",
        destination_address_prefix="*",
        resource_group_name= resource_group2.name,
        network_security_group_name= network_security_group.name)

subnet_network_security_group_association = azure.network.SubnetNetworkSecurityGroupAssociation("NSG_Association",
    subnet_id= net.subnets[0].id,
    network_security_group_id= network_security_group.id)