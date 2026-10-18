export const organizationSettingsEvent = 'ordivant:organization-settings';

/** Request the mounted settings controller without moving the product or resource. */
export function openOrganizationSettings(): void {
  window.dispatchEvent(new Event(organizationSettingsEvent));
}
