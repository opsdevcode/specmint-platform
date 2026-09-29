mint v0
namespace example.main
import example.a as lib
import example.b as lib
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Duplicate import alias"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
