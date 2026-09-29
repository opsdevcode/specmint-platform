mint v0
namespace example.ext
extension ext.sample v2alpha1
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Require an unsupported extension version"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
