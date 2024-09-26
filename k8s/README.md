# Installing MicroK8s

`sudo apt update`

`sudo apt upgrade -y`

`sudo snap install microk8s --clasic --chanel=1.28`

`sudo usermod -a -G microk8s <USERNAME>`

`echo "alias kubectl='microk8s.kubectl'" >> ~/.bashrc`

`microk8s enable registry`

`microk8s.enable dns`

`microk8s.enable ingress`

`microk8s.enable gpu`

`kubectl describe daemonset nvidia-device-plugin-daemonset -n kube-system`
