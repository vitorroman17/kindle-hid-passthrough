from nuitka.plugins.PluginBase import NuitkaPluginBase


class NuitkaPluginBytecodeLargeModules(NuitkaPluginBase):
    plugin_name = "bytecode-large-modules"
    plugin_desc = "Ship named modules as bytecode instead of compiling them to C."

    BYTECODE_MODULES = ("bumble.hci",)

    @staticmethod
    def isAlwaysEnabled():
        return True

    def decideCompilation(self, module_name):
        if module_name in self.BYTECODE_MODULES:
            return "bytecode"
        return None
