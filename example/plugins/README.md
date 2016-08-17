# Zappa Plugin Example

The code in this directory is an example of a plugin for `zappa`.  
It's in it's early stages at this point, so use at your own risk.

## setup.py
In your `setup.py` file, you will need a couple of things.  First you will need to specify `zappa` in your
install_requires section.

Second, you will need to specify the entry_points for your plugin.  The entry point for zappa plugins is `zappa.plugins`.
You can have a look at the `setup.py` file in this directory for an example.  Each command will need it's own line in the
entry points section.

## Click Command
Your plugin will define a click command that will be added to `zappa` command.  For example, if you add command called
`example`, as in this example plugin, you will be able to execute it as `zappa example`.

You are not limited to `@click.command`.  You can use `@click.group` as well.
And, of course, you can also add any options and/or arguments you like.

## Click Context Object
Your click command can optionally take a click context.  You can ensure that you get the context
by using the `@click.pass_context` decorator, and having a `ctx` argument to your function.

The structure of the context object:
```
ctx.obj.yes => bool (result of the -y/--yes option)
ctx.obj.settings => path (result of the -s/--settings option)
ctx.obj.loader => function (Returns a ZappaLoader obj that can be used to perform various operations, TBD)
``` 
