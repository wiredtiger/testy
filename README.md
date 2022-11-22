# testy
A WiredTiger test framework to run 24/7 workloads
<img src="https://user-images.githubusercontent.com/15895661/200436292-66c87f0d-3068-4bae-a002-3de473faf8b5.png" align="right">

## Setup
Running testy requires two machines: a local machine from which to run the `fab` commands and a remote machine where the testy framework lives. Your local machine should be your Mac laptop and not an evergreen workstation. We have not yet tested running Fabric on Windows.

- Spawn an Ubuntu 18.04/20.04 [evergreen host](https://spruce.mongodb.com/spawn/host) to use for your remote machine. 

- On your local machine, install the python packages needed to run Fabric commands:
  ```
  python3 -m pip install fabric invocations
  ```

- Run the install command from your local machine:
  ```
  fab -H user@host install
  ```
  where user@host is the user and host name used to log into the remote evergreen host (it looks something like `ubuntu@ec2-7-21-20-75.ap-southeast-2.compute.amazonaws.com`).
