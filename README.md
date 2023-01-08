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

## Running testy

You can upload a [workload](#using-fab-workload) or use an existing workload in the testy framework. If the workload requires the database to be populated before starting, do this first. If either process fails, an error message will be returned.

- The `start` function takes a required workload argument. The function executes the `run()` function as defined in the workload interface file, and also starts the backup and crash testing services. Running the workload, database backups and crash testing are managed on the remote server by linux `systemd` services.

- The `populate` function takes a required workload argument. This function executes on the the `populate()` function as defined in the workload interface file to populate the database required for the workload. 

  ```
  fab -H user@host populate <workload>
  fab -H user@host start <workload>
  ```

If a workload is already running, the start function will not work. Either call `restart` or `stop`. 

- The `restart` function takes an optional workload argument to restart the framework on. If no argument is given, the current workload will be used for the new run. The restart function will also run `validate()` as implemented by the user's workload interface file. If this is not successful, an error message will be returned and restart will be aborted. 

  ```
  fab -H user@host restart [workload]
  ```

- The `stop` function does not take any arguments and will stop the running workload and testy framework.
  ```
  fab -H user@host stop
  ```
-  The `info` function allows you to see information relating to the testy service. This function will print the current wiredtiger and testy branch and commit hash, the current workload, and the testy service status. This function takes no arguments.
    ```
    fab -H user@host info
    ```

## Using `fab workload`
The workload function has three options: upload, list and describe. If no option is given it will return the current workload by default. Up to three options can be given at a time in any order but they will be executed in the order of (1) upload, (2) list, and (3) describe. If one option fails, an error message will be printed and the other options will continue to execute. 

  ```
  fab -H user@host workload [--upload=<required-argument>] [--list] [--describe=[optional-argument]]

  # This will return the current workload
  fab -H user@host workload
  ```

- The `workload --upload` requires one argument, the compressed workload folder. The function will upload a workload from your local network to the remote testy server. You will need an archive containing a `workload` directory with a workload interface file ({workload}.sh), and any other files needed to run the workload. The `workload` directory and workload interface file are required to share the same name to operate. Testy can extract most compressed file types. This will extract the files in the framework's '/workloads' directory, inside a folder named after the workload. The function will print an error message on failure, and delete any traces of the failed upload from the remote server. 
  ```
  fab -H user@host workload [--upload=<workload.zip>]
  ```

- The `workload --list` function will list all available workloads on the testy server, highlighting the current workload selected. This option does not take any arguments. 
  ```
  fab -H user@host workload [--list]
  ```

- The `workload --describe` function takes an optional workload name as an argument and will describe the given workload. If no argument is given, the current workload will be used. If there is no current workload, an error message will be printed. This description will be implemented by the user in the workload's workload interface file `{workload}.sh`. If not implemented, the function will not be able to describe the workload. 
  ```
  fab -H user@host workload [--describe=[workload]]
  ```


## Updating testy

- The `update` function allows you update the wiredTiger and/or testy source on the remote. This function can take two optional arguments, a wiredTiger branch and/or a testy branch and will update the current branch to these supplied branches. The `update` function will stop the current workload, update the branches and start the workload again in its function. If no arguments are provided, no updates will be made. 
  ```
  fab -H user@host update [--wiredtiger-branch=<branch>] [--testy-branch=<branch>]
  ```


## Adding functions to fabfile.py

We use [Fabric](https://www.fabfile.org/) -- a high-level Python library designed to execute shell commands remotely over SSH -- to manage our remote `testy` server. The `testy` commands are defined as `fabric` task functions in the file `fabfile.py`. We illustrate creating a new `testy` function in the example below.

To add new functionality in fabfile.py follow the structure: 

  ```
  @task
  def describe(c, workload_name)
      # Full path to the workload interface file. 
      wif = f"testy/workloads/{workload_name}/{workload_name}.sh"

      # Call on the describe() function in the workload interface file
      command = wif + " describe"
      result = c.run(command, user=user, warn=True)

      # This will print the result to your local terminal.
      if not result: 
          print(f"Unable to describe '{workload_name}' workload.")
      elif result.stdout == "":
          print(f"No description provided for workload '{workload_name}'.")

  ```
  In the terminal we can call this new function `describe` like so:  
  ```
  # Note that underscores in function arguments are converted to dashes on the command line.  
  fab -H user@host describe <--workload-name=sample>
  ```

Fabric tasks require a context object as the first argument followed by zero or more user-defined arguments. The context object (passed in as `c` in the example above) is used to share parser and configuration state with executed tasks and provides functions to execute commands on the remote server, such as `c.run()`.
- You can also add additional arguments that give the user ability to pass arguments into these fabric functions as well. 

Fabric allows you to execute shell commands both on the remote server and locally. 

- When you would like to execute a command on the remote server, you will used the connection argument `c` passed in and can execute commands such as `c.sudo()` or  `c.run()` etc. 

More information on fabric commands can be found here: https://docs.fabfile.org/en/stable/
