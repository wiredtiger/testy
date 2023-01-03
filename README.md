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

## Using workloads
The workload function has 3 options: upload, list and describe. If no option is given it will return the current workload by default. Up to 3 options can be given at a time in any order but they will be executed in the order of 1. upload, 2.list, and 3. describe. If one option fails, an error message will be printed and the other options will continue to execute. 

  ```
    fab -H user@host workload --upload={required-argument} --list --descibe={optional-argument}

    # This will return the current workload
    fab -H user@host workload
  ```

- The `workload --upload` requires one argument, the compressed workload folder. The function will upload a workload from your local network to the remote testy server, you will need a zip folder containing a <workload> directory with a <workload>.sh file, and any other files needed to run the workload. The <workload> directory and <workload>.sh file are required to share the same name to operate. The current implementation can extract most compressed file types, and will extract the files in the framework's '/workloads' directory, inside a folder named after the workload. The function will print an error message on failure, and delete any traces of the failed upload from the testy framework. 
  ```
   fab -H user@host workload --upload={workload}.{zip}
  ```

- The `workload --list` function will list all available workloads on the testy server, highlighting the current workload selected. This option does not take any arguments. 
  ```
   fab -H user@host workload --list
  ```

- The `workload --describe` function takes an optional workload name as a required argument and will describe the given workload. If no argument is given, the current workload will be used. If there is no current workload, an error message be printed. This description will be implemented by the user in the workload's workload interface face <workload>.sh in the given <workload>'s directory, if not implemented the function will not be able to describe the workload. 
  ```
   fab -H user@host workload --descibe={workload}
  ```

## Running a workload 

Once a workload has been uploaded successfully with the correct files, you can start the workload. If a workload needs to be populated before starting, do this first. Both `populate` and `start` functions require a workload as a given argument. If either process fails, an error message will be returned.

  ```
  fab -H user@host populate {workload} 
  fab -H user@host start {workload} 
  ```

If a workload is already running, the start function will not work. Either call `restart` or call `stop` to call `start` again. 

- The `restart` function takes an optional workload argument to restart the framework on. If no argument is given, the current workload will be used for the new run. The restart function will also run `validate()` as implemented by the user's workload interface file. If this is not successful, an error message will be returned and restart will be aborted. 

  ```
  fab -H user@host restart {workload}
  ```

- The `stop` function does not take any arguments and will stop the running workload.
  ```
  fab -H user@host stop
  ```

## Other Commands 

- The `update` function allows you update the WiredTiger and/or Testy source on the framework. This function can take two optional arguments, a WiredTiger branch and/or a Testy branch and will update the current branch to these supplied branches. The `update` function will stop the current workload, update the branches and start the workload again in its function. If no argumnets are provided, no updates will be made. 
  ```
  # Note that arguments named with '_' will need to changed to '-' in the call from terminal. 
  fab -H user@host update --wiredtiger-branch={branch} --testy-branch={branch}
  ```

-  The `info` function allows you to see information relating to the testy service. This function will print the current WiredTiger and Testy branch and commit hash, the current workload, and the testy service status. This function takes no arguments.
    ```
    fab -H user@host info
    ```

# Adding changes to fabfile.py

To add a new functionality in fabfile.py follow the structure: 

  ```
  @task
  def new_function(c, additional_arguments):

      c.command()
      local()

  ```

The fab function requires a connection argument passed in such as `c` in the example above, this is the connection to the remote server. All executable fabric functions will need this argument. 
- You can also add additional arguments that give the user ability to pass arguments into these fabric functions as well. 

Fabric allows you to execute shell commands both on the remote server and locally. 

- When you would like to execute a command on the remote server, you will used the connection argument `c` passed in and can execute commands such as `c.sudo()` or  `c.run()` etc. 

- To execute commands locally, use the `local()` command. 

More inforamtion on fabric commands can be found here: https://docs.fabfile.org/en/1.11/tutorial.html
