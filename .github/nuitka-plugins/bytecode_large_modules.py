from nuitka.plugins.PluginBase import NuitkaPluginBase


class NuitkaPluginBytecodeLargeModules(NuitkaPluginBase):
    plugin_name = "bytecode-large-modules"
    plugin_desc = "Ship bumble as bytecode instead of compiling it to C."

    # Compiled, not bytecode. Pairing runs ECDH P-256 in pure python here since
    # cryptography was dropped, and interpreting it makes pairing measurably slower.
    COMPILED_PREFIXES = ("bumble.crypto",)

    @staticmethod
    def isAlwaysEnabled():
        return True

    def decideCompilation(self, module_name):
        name = str(module_name)
        if name != "bumble" and not name.startswith("bumble."):
            return None
        for prefix in self.COMPILED_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                return None
        return "bytecode"
