mint v0
namespace example.main
import example.missing
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Import a unit that is not in the compiler inputs"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
