# Source vendor paths without discarding command overrides from the caller.
__flagos_inherited_path="$PATH"
for f in /etc/profile.d/*.sh; do [ -r "$f" ] && . "$f"; done
__flagos_vendor_path="$PATH"
PATH="$__flagos_inherited_path"
for __flagos_dir in ${__flagos_vendor_path//:/ }; do
    [ -n "$__flagos_dir" ] || continue
    case ":$PATH:" in
        *":$__flagos_dir:"*) ;;
        *) PATH="$PATH:$__flagos_dir" ;;
    esac
done
export PATH
unset __flagos_inherited_path __flagos_vendor_path __flagos_dir
