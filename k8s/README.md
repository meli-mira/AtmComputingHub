# Installing MicroK8s

`sudo apt update`

`sudo apt upgrade -y`

`sudo snap install microk8s --classic --channel=1.28`

`sudo usermod -a -G microk8s <USERNAME>`

`echo "alias kubectl='microk8s.kubectl'" >> ~/.bashrc`

`microk8s enable registry`

`microk8s.enable dns`

`microk8s.enable ingress`

`microk8s.enable gpu`

`kubectl describe daemonset nvidia-device-plugin-daemonset -n kube-system`

`kubectl label node <NODE_NAME> gpu-type=<GPU_TYPE>`


`microk8s enable rook-ceph`

`microk8s connect-external-ceph`

`sudo mktemp -p /media/hdd2/ceph_data XXXX.img`

`sudo truncate -s 1700G /media/hdd2/ceph_data/onsp.img`

`sudo losetup --show -f /media/hdd2/ceph_data/onsp.img`

>> /dev/loop39

`sudo mknod -m 0660 /dev/sdia b 7 39`

`sudo microceph disk add --wipe /dev/sdia`
