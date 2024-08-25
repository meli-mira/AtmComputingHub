import gradio as gr
import webbrowser
from kubernetes import client, config

class KubeClient:
    def __init__(self):
        # Load in-cluster config
        config.load_kube_config(config_file='/var/snap/microk8s/current/credentials/client.config')
        # Create an API client
        self.apps_client = client.AppsV1Api()
        self.core_client = client.CoreV1Api()
        self.net_client = client.NetworkingV1Api()

    def get_deployment_limits(self, deploy):
        deployment_description = self.apps_client.read_namespaced_deployment(name=deploy.metadata.name, namespace='default')
        container = deployment_description.spec.template.spec.containers[0]
        cpu_limit = container.resources.limits.get('cpu', 'Not set')
        memory_limit = container.resources.limits.get('memory', 'Not set')
        gpu_limit = container.resources.limits.get("nvidia.com/gpu", 'Not set')

        node_selector = deployment_description.spec.template.spec.node_selector
        gpu_type = node_selector.get('gpu-type', 'Not set') if node_selector else 'Not set'
        gpu_limit = f"{gpu_limit}x{gpu_type.upper()}"
        
        status = 'Undefined'
        try:
            labels = deploy.spec.selector.match_labels
            label_selector = ",".join([f"{k}={v}" for k, v in labels.items()])
            pods = self.core_client.list_namespaced_pod(namespace='default', label_selector=label_selector)
            state = pods.items[0].status.container_statuses[0].state
            if state.waiting:
                status = 'Waiting'
            elif state.running:
                status = 'Running'
            elif state.terminated:
                status = 'Terminated'
        except Exception as exception:
            print(f'Failed to get pod status: {exception}')
        
        return {'cpu_limit' : cpu_limit, 'memory_limit' : memory_limit, 'gpu_limit' : gpu_limit, 'status' : status}

    def get_deployments(self):
        deployments = self.apps_client.list_namespaced_deployment(namespace='default')
        deployments_descriptions = []
        for deploy in deployments.items:
            desc = {
                'name': deploy.metadata.name,
                'status': 'Running' if deploy.status.ready_replicas == deploy.status.replicas else 'Stopped'
            }
            desc.update(self.get_deployment_limits(deploy))
            deployments_descriptions.append(desc)
        
        return deployments_descriptions

    def create_workspace(self, deployment_name):
        assert isinstance(deployment_name, str) and len(deployment_name) > 5
        service_name = f"{deployment_name}-service"
        ingress_name = f"{deployment_name}-ingress"
        # Create a V1Deployment object
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=deployment_name, labels={"app": deployment_name}),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": deployment_name}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": deployment_name}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name=deployment_name,
                                image="jupyter/datascience-notebook:x86_64-ubuntu-22.04", #"localhost:32000/k40:latest",
                                ports=[client.V1ContainerPort(container_port=8888)],
                                resources=client.V1ResourceRequirements(
                                    limits={
                                        "cpu": "16",             # 16 CPU cores
                                        "memory": "32Gi",        # 32 GB of RAM
                                        "nvidia.com/gpu": "2"    # 2 GPUs
                                    }
                                ),
                            )
                        ],
                        node_selector={"gpu-type": "k80"}
                    )
                )
            )
        )
        
        response = self.apps_client.create_namespaced_deployment(body=deployment, namespace="default")

        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(name=service_name),
            spec=client.V1ServiceSpec(
                selector={"app": deployment_name},
                ports=[client.V1ServicePort(
                    protocol="TCP",
                    port=8888, # Eposed port
                    target_port=8888 # Container port
                )],
                type="ClusterIP" #"ClusterIP" # Change this to "NodePort" or "LoadBalancer" if needed
            )
        )
    
        # Create the service in the specified namespace
        response = self.core_client.create_namespaced_service(namespace="default", body=service)
        
        ingress = client.V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=client.V1ObjectMeta(name=ingress_name), #, annotations={'kubernetes.io/ingress.class': 'public'}),
            spec=client.V1IngressSpec(
                rules=[
                    client.V1IngressRule(
                        host=f"{deployment_name}.10.13.0.100.nip.io",
                        http=client.V1HTTPIngressRuleValue(
                            paths=[
                                client.V1HTTPIngressPath(
                                    path="/",
                                    path_type="Prefix",
                                    backend=client.V1IngressBackend(
                                        service=client.V1IngressServiceBackend(
                                            name=service_name,
                                            port=client.V1ServiceBackendPort(number=8888)
                                        )
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
    
        # Create the Ingress in the specified namespace
        response = self.net_client.create_namespaced_ingress(
            body=ingress, 
            namespace="default"
        )
        return response

    def delete_workspace(self, deployment_name):
        assert isinstance(deployment_name, str) and len(deployment_name) > 5
        service_name = f"{deployment_name}-service"
        ingress_name = f"{deployment_name}-ingress"
    
        # Delete the Ingress
        self.net_client.delete_namespaced_ingress(
            name=ingress_name,
            namespace="default"
        )

        # Delete the Service
        self.core_client.delete_namespaced_service(
            name=service_name,
            namespace="default"
        )

        self.apps_client.delete_namespaced_deployment(
            name=deployment_name,
            namespace="default",
            body=client.V1DeleteOptions(
                propagation_policy='Foreground',  # Ensures that all associated resources are deleted
                grace_period_seconds=0  # Optional: Immediately delete the deployment
            )
        )




kubeClient = KubeClient()

UI_WORKSPACE_SLOTS = 50

def create_workspace(email):
    if not email:
        return "Error: The email field is required."
    email = email.split("@")[0]
    name = email.replace('.', '-')
    kubeClient.create_workspace(f"workspace-{name}")
    return "Workspace created. Wait 5 minutes and refresh."

def delete_workspace(workspace_name):
    print(workspace_name)
    kubeClient.delete_workspace(workspace_name)
    return "Workspace deleted. Wait 5 minutes and refresh."

# def open_workspace_link(workspace_name):
#     # Open a URL in a new tab
#     print(f"{workspace_name}.10.13.0.100.nip.io")
#     webbrowser.open(f"{workspace_name}.10.13.0.100.nip.io", new=2)
#     print("gata")
    

def refresh_ui():
    workspaces = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_cpu = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_mem = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_gpu = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    status_list = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_launch = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_start = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_stop = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_delete = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]

    deployments = kubeClient.get_deployments()
    for i, deploy in enumerate(deployments):
        workspaces[i] = gr.update(value=deploy['name'], visible=True)
        limits_cpu[i] = gr.update(value=deploy['cpu_limit'], visible=True)
        limits_mem[i] = gr.update(value=deploy['memory_limit'], visible=True)
        limits_gpu[i] = gr.update(value=deploy['gpu_limit'], visible=True)
        status_list[i] = gr.update(value=deploy['status'], visible=True)
        buttons_launch[i] = gr.update(visible=True, link=f"http://{deploy['name']}.10.13.0.100.nip.io")
        buttons_start[i] = gr.update(visible=True)
        buttons_stop[i] = gr.update(visible=True)
        buttons_delete[i] = gr.update(visible=True)
        
    status = f"The cluster is running {len(deployments)} workspaces."
    return workspaces + limits_cpu + limits_mem + \
        limits_gpu + status_list + buttons_launch + \
        buttons_start + buttons_stop + buttons_delete + [status]


with gr.Blocks() as demo:
    gr.Markdown("# ATM Computing Hub")

    workspaces = []
    workspaces_buttons_start = []
    workspaces_buttons_stop = []
    workspaces_buttons_delete = []
    workspaces_buttons_launch = []
    workspaces_limits_cpu = []
    workspaces_limits_mem = []
    workspaces_limits_gpu = []
    workspaces_status = []

    with gr.Row():
        server_status = gr.Textbox(label="Kube status")
        refresh_button = gr.Button("Refresh")

    with gr.Accordion("Create new workspace", open=False):
        with gr.Row():
            create_panel_cpu_count = gr.Number(label="Num CPUs:", value=16)
            create_panel_mem_count = gr.Number(label="Memory (GB):", value=32)
            create_panel_gpu_type = gr.Dropdown(label="GPU Type", choices=['K40', 'K80'], value='K80', interactive=True)
            create_panel_gpu_count = gr.Number(label="Num GPUs:", value=2)
            create_panel_email = gr.Textbox(label="Email (@mta):", value='')
        create_button = gr.Button("Create Workspace")
        # create_panel_status = gr.Markdown("x")
    
    with gr.Column():
        with gr.Row():
            gr.Markdown("**Workspaces**")
            gr.Markdown("**CPU**")
            gr.Markdown("**Mem**")
            gr.Markdown("**GPU**")
            gr.Markdown("**Status**")
            gr.Markdown("**Actions**")
        
        for i in range(UI_WORKSPACE_SLOTS):
            with gr.Row():
                workspace_name = gr.Markdown(visible=False)
                workspaces.append(workspace_name)
                workspaces_limits_cpu.append(gr.Markdown(visible=False))
                workspaces_limits_mem.append(gr.Markdown(visible=False))
                workspaces_limits_gpu.append(gr.Markdown(visible=False)) # GPU
                workspaces_status.append(gr.Markdown(visible=False))
                
                launch_button = gr.Button("Launch🚀", visible=False)
                workspaces_buttons_launch.append(launch_button)
                # launch_button.click(open_workspace_link, inputs=workspace_name)
                
                
                workspaces_buttons_start.append(gr.Button("Start", visible=False))
                workspaces_buttons_stop.append(gr.Button("Stop", visible=False))

                delete_button = gr.Button("Delete", visible=False)
                workspaces_buttons_delete.append(delete_button)
                delete_button.click(delete_workspace, inputs=workspace_name, outputs=server_status)
    
    workspaces_outputs = workspaces +  workspaces_limits_cpu + workspaces_limits_mem + \
        workspaces_limits_gpu + workspaces_status + workspaces_buttons_launch + \
        workspaces_buttons_start + workspaces_buttons_stop + workspaces_buttons_delete + [server_status]
    refresh_button.click(refresh_ui, outputs=workspaces_outputs)
    
    create_button.click(create_workspace, inputs=create_panel_email, outputs=server_status)

demo.launch(server_name="0.0.0.0", server_port=8000)