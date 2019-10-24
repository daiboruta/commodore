# Local mode

Commodore provides a local mode for the `compile` command. Local mode is
intended for local development, and will not fetch information from the
SYNventory API or clone Git repositories for the inventory and components.


Local mode can be enabled with the `--local` flag of the `compile` command.
The flag takes an argument which specifies the Kapitan target to render.

```shell
pipenv run commodore compile <customer> <cluster> --local <target>
```

Valid targets can be determined with

```shell
find inventory/targets -name '*.yml'
```

In local mode, the existing directory structure in the working directory is
used.  This allows local development on components and also allows testing
local modifications to the inventory.  The user is responsible for ensuring
that all the moving parts are where they should be.  It is recommended to run
Commodore in regular mode once to fetch all the inputs which are required to
compile the catalog for the selected cluster.

```shell
pipenv run commodore compile <customer> <cluster>
```