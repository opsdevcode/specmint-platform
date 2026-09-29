mint v0
namespace example.ext
extension ext.sample v1alpha1
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Use a recognized namespaced extension capability"
  use ext.sample.tag v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
