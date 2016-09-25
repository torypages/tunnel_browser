from subprocess import check_output
import argparse
import configparser
import digitalocean
import logging
import os
import subprocess
import time


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('tunnel-browser')

config = configparser.ConfigParser()

config.read("config.ini")

api_key = config.get('main', 'api_key')
ssh_key_name = config.get('main', 'ssh_key_name')
droplet_name = config.get('main', 'droplet_name')
browser_dir = config.get('main', 'browser_dir')
ssh_key = config.get('main', 'ssh_key')
proxy_port = config.get('main', 'proxy_port')
ssh_username = config.get('main', 'ssh_username')
default_page = config.get('main', 'default_page')


parser = argparse.ArgumentParser()
parser.add_argument('--start', action='store_true')
parser.add_argument('--stop', action='store_true')
parser.add_argument('--keys', action='store_true')
parser.add_argument('--droplets', action='store_true')
parser.add_argument('--ip', action='store_true')
parser.add_argument('--launch', action='store_true')
parser.add_argument('--kill-port', action='store_true')

args = parser.parse_args()


def create_droplet():
    manager = digitalocean.Manager(token=api_key)
    keys = manager.get_all_sshkeys()
    ssh_key = [i for i in keys if i.name == ssh_key_name][0]
    droplet = digitalocean.Droplet(token=api_key,
                                   name=droplet_name,
                                   region='tor1', # Toronto
                                   image='ubuntu-16-04-x64', # Ubuntu 16.04 x64
                                   size_slug='512mb',  # 512MB
                                   ssh_keys=[ssh_key],
                                   backups=False)
    droplet.create()


def get_droplet_ip():
    logger.info("Will wait until status is active.")
    while True:
        manager = digitalocean.Manager(token=api_key)
        for i in manager.get_all_droplets():
            if i.name == droplet_name:
                if i.status == 'active':
                    logger.info(i.ip_address)
                    return i.ip_address
                else:
                    logger.info("Still waiting...")
                    time.sleep(1)


def start(create=True):
    if create:
        create_droplet()
    return get_droplet_ip()


def stop():
    manager = digitalocean.Manager(token=api_key)
    my_droplets = manager.get_all_droplets()
    for droplet in my_droplets:
        droplet.destroy()


def list_keys():
    manager = digitalocean.Manager(token=api_key)
    keys = manager.get_all_sshkeys()
    for i in keys:
        logger.info(i)
        import pdb; pdb.set_trace()


def list_droplets():
    manager = digitalocean.Manager(token=api_key)
    for i in manager.get_all_droplets():
        # i.status == 'active' when up
        logger.info(i)


def print_ip():
    manager = digitalocean.Manager(token=api_key)
    for i in manager.get_all_droplets():
        if i.name == droplet_name:
            logger.info(i.ip_address)
            return


def get_pid():
    try:
        netstat_cmd = "netstat -nlp"
        result_full = subprocess.check_output(netstat_cmd.split())
        result_split = result_full.split(b'\n')
        result = [i for i in result_split
                  if "127.0.0.1:{}".format(proxy_port) in str(i)]
        pid = result[0].split()[-1].split(b'/')[0]
        return pid
    except Exception:
        logger.error("Could not get pid of tunnel")
        return None


def call_with_retry(cmd, sleep=5, retries=5):
    msg = "Trying command {}".format(cmd)
    logger.info(msg)
    while retries:
        result = subprocess.call(cmd.split())
        if not result:
            logger.info("Command success!")
            break
        logger.info("Rerying command {}".format(cmd))
        retries -= 1
        time.sleep(sleep)

    if not retries:
        msg = "Command {} failed, aborting".format(cmd)
        raise Exception(msg)


def kill_port_process():
    pid = get_pid()
    kill_cmd = 'kill {}'.format(str(pid, 'utf-8'))
    call_with_retry(kill_cmd)


def port_is_free(port):
    return not bool(get_pid())


def launch():
    if not port_is_free(proxy_port):
        msg = "Port {} is busy".format(proxy_port)
        raise Exception(msg)

    ip_address = start()

    ssh_cmd = ('ssh -i {ssh_key} -oStrictHostKeyChecking=no -D {proxy_port} '
               '-N -f {username}@{ip_address}'
               .format(proxy_port=proxy_port, username=ssh_username,
                       ssh_key=ssh_key, ip_address=ip_address))
    call_with_retry(ssh_cmd)

    chrome_cmd = ('google-chrome --user-data-dir={} '
                  '--proxy-server=socks5://127.0.0.1:{} {}'
                  .format(browser_dir, proxy_port, default_page))
    os.makedirs(browser_dir, exist_ok=True)
    subprocess.call(chrome_cmd.split())

    kill_port_process()
    stop()
    logger.info("Finshed!")


if __name__ == '__main__':

    if args.start:
        start()
    elif args.launch:
        launch()
    elif args.kill_port:
        kill_port_process()
    elif args.stop:
        stop()
    elif args.keys:
        list_keys()
    elif args.droplets:
        list_droplets()
    elif args.ip:
        print_ip()
