from unicodedata import name
import pulumi_azure as azure
import pulumi_azure_native as az
from pulumi import Config, Output, export
import base64
from operator import truediv

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Load Balanced Server Part \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

config = Config()
username = config.require("username")
password = config.require("password")

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Resource Group Number 2 \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
resource_group2 = az.resources.ResourceGroup(
    "Server_RG", resource_group_name='Server_RG')

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\ Virtual Network and LB roules\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
net = az.network.VirtualNetwork(
    resource_name = "server-network",
    virtual_network_name="server-network",
    resource_group_name=resource_group2.name,
    address_space=az.network.AddressSpaceArgs(
        address_prefixes=["10.0.0.0/16"],
    ),
    subnets=[az.network.SubnetArgs(
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
while i <4:
    i += 1
    
    network_iface = az.network.NetworkInterface(
        resource_name=f"server-nic{i}",
        network_interface_name=f"server-nic{i}",
        resource_group_name=resource_group2.name,
        ip_configurations=[az.network.NetworkInterfaceIPConfigurationArgs(
            name=f"webserveripcfg{i}",
            subnet=az.network.SubnetArgs(id=net.subnets[0].id),
            private_ip_allocation_method=az.network.IPAllocationMethod.DYNAMIC,
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

    vm = azure.compute.VirtualMachine(
        name=f"VirtualMachine{i}",
        resource_name=f"VirtualMachine{i}",
        location= resource_group2.location,
        resource_group_name= resource_group2.name,
        network_interface_ids=[network_iface.id],
        vm_size="STANDARD_B2S",
        storage_image_reference=azure.compute.VirtualMachineStorageImageReferenceArgs(
            publisher="Canonical",
            offer="UbuntuServer",
            sku="16.04-LTS",
            version="latest",
        ),
        storage_os_disk=azure.compute.VirtualMachineStorageOsDiskArgs(
            name = f"myosdisk{i}",
            caching="ReadWrite",
            create_option="FromImage",
            managed_disk_type="Standard_LRS",
        ),
        os_profile=azure.compute.VirtualMachineOsProfileArgs(
            computer_name=f"hostname{i}",
            admin_username=username,
            admin_password=password,
            custom_data=base64.b64encode(
                init_script.encode("ascii")).decode("ascii"),
        ),
        os_profile_linux_config=azure.compute.VirtualMachineOsProfileLinuxConfigArgs(
            disable_password_authentication=False,
        ),
        )


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