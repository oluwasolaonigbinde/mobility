// Version 1 is immutable. Legal-pack approval remains tracked internally in REQ-032.
export const DRIVER_AGREEMENT_VERSION = "1";
export const DRIVER_AGREEMENTS: Record<string, { title: string; text: string }[]> = {
  "1": [
    {
      title: "Working with Terrax Media",
      text: "You work as an independent contractor. You choose whether to accept a job. Your job offer sets out the car, dates, advert and payment terms for that job.",
    },
    {
      title: "Your pay",
      text: "Your job offer shows how much you can earn. Pay depends on the driving we verify under those terms. We pay into your checked bank account. Tell Terrax Media if your bank details change or you think a payment is wrong.",
    },
    {
      title: "Your trips",
      text: "GPS is tracked only while you are on a trip. Start a trip when you begin driving for the job and end it when you finish. We use trip locations to check driving and report campaign results.",
    },
    {
      title: "The advert on your car",
      text: "Keep the advert on your car for the agreed job. Take care of it and tell Terrax Media if it is damaged, removed or cannot stay on the car. Follow the job instructions for installation, photos and removal.",
    },
    {
      title: "Your details and privacy",
      text: "You agree to our use of your identity documents, contact details, car details, bank details and trip locations to check your application, run trips and pay you. Terrax Media staff review your application and bank details. Contact Terrax Media through Help if you have a question about your information or want to discuss your consent.",
    },
  ],
};
export const DRIVER_AGREEMENT_POINTS = [
  "You work as an independent contractor.",
  "Your job offer shows how much you can earn. Pay depends on the driving we verify.",
  "GPS is tracked only while you are on a trip.",
  "Keep the advert on your car for the agreed job.",
  "You agree to our use of your details to check your application, run trips and pay you.",
];
