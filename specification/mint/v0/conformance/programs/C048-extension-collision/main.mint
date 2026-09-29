mint v0
namespace example.ext
extension ext.sample v1alpha1
automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Duplicate extension namespace in the registry"
  use ext.sample.tag v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
