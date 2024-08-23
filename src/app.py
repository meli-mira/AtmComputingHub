import gradio as gr


from kubernetes import client, config

class KubeClient:
    def __init__(self):
        # Load in-cluster config
        config.load_kube_config(config_file='/var/snap/microk8s/current/credentials/client.config')
        # Create an API client
        self.api_client = client.AppsV1Api()

    def get_deployment_limits(self, deploy):
        deployment_decription = self.api_client.read_namespaced_deployment(name=deploy.metadata.name, namespace='default')
        container = deployment_decription.spec.template.spec.containers[0]
        cpu_limit = container.resources.limits.get('cpu', 'Not set')
        memory_limit = container.resources.limits.get('memory', 'Not set')
        gpu_limit = container.resources.limits.get("nvidia.com/gpu", 'Not set')
        return {'cpu_limit' : cpu_limit, 'memory_limit' : memory_limit, 'gpu_limit' : gpu_limit}

    def get_deployments(self):
        deployments = self.api_client.list_namespaced_deployment(namespace='default')
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
                                image="localhost:32000/k40:latest",
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
        
        response = self.api_client.create_namespaced_deployment(body=deployment, namespace="default")


kubeClient = KubeClient()

UI_WORKSPACE_SLOTS = 50

def create_workspace(email):
    if not email:
        return "Error: The email field is required."
    email = email.split("@")[0]
    name = email.replace('.', '-')
    kubeClient.create_workspace(f"workspace-{name}")
    return "Workspace created. Wait 5 minutes and refresh."
    

def refresh_ui():
    workspaces = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_cpu = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_mem = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    limits_gpu = [gr.update(value='', visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_start = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]
    buttons_stop = [gr.update(visible=False) for _ in range(UI_WORKSPACE_SLOTS)]

    deployments = kubeClient.get_deployments()
    for i, deploy in enumerate(deployments):
        workspaces[i] = gr.update(value=deploy['name'], visible=True)
        limits_cpu[i] = gr.update(value=deploy['cpu_limit'], visible=True)
        limits_mem[i] = gr.update(value=deploy['memory_limit'], visible=True)
        limits_gpu[i] = gr.update(value=deploy['gpu_limit'], visible=True)
        buttons_start[i] = gr.update(visible=True)
        buttons_stop[i] = gr.update(visible=True)
        
    status = f"The cluster is running {len(deployments)} workspaces."
    return workspaces + limits_cpu + limits_mem + \
        limits_gpu + \
        buttons_start + buttons_stop + [status]


with gr.Blocks() as demo:
    gr.Markdown("# ATM Computing Hub")

    workspaces = []
    workspaces_buttons_start = []
    workspaces_buttons_stop = []
    workspaces_limits_cpu = []
    workspaces_limits_mem = []
    workspaces_limits_gpu = []

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
                workspaces.append(gr.Markdown(visible=False))
                workspaces_limits_cpu.append(gr.Markdown(visible=False))
                workspaces_limits_mem.append(gr.Markdown(visible=False))
                workspaces_limits_gpu.append(gr.Markdown(visible=False)) # GPU
                workspaces_buttons_start.append(gr.Button("Start", visible=False))
                workspaces_buttons_stop.append(gr.Button("Stop", visible=False))
    
    workspaces_outputs = workspaces +  workspaces_limits_cpu + workspaces_limits_mem + \
        workspaces_limits_gpu + \
        workspaces_buttons_start + workspaces_buttons_stop + [server_status]
    refresh_button.click(refresh_ui, outputs=workspaces_outputs)
    
    create_button.click(create_workspace, inputs=create_panel_email, outputs=server_status)

demo.launch(server_name="0.0.0.0", server_port=8000)