mint v0
namespace example.a
import example.b
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Cycle A"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
