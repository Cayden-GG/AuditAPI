
def client_confirmation(client_name, target_url):
    # create html template and email subject line
    pass

def client_audit_results(client_name, target_url, audit_results):
    # create html template and email subject line
    pass

def client_audit_failed(client_name, target_url):
    # create html template and email subject line
    # if the error is regarding invalid sitemap or robots.txt, meaning we cannot fix the issue mention this to the client. 
    # else say fixing the problem.
    pass
# example valvanta branded email:
# htmlContent = f"""
#     <!DOCTYPE html>
#     <html>
#     <head>
#       <meta charset="utf-8">
#       <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     </head>
#     <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
#       <div style="background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
#         <h1 style="color: white; margin: 0; font-size: 24px;">Valvanta Digital</h1>
#         <p style="color: #a0c4b8; margin: 10px 0 0 0;">Digital Made Simple. Presence Made Powerful.</p>
#       </div>
#
#       <div style="background: #ffffff; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
#         <h2 style="color: #2d3748; margin-top: 0;">Hi {data.name},</h2>
#
#         <p>Thank you for reaching out to Valvanta Digital! We've received your inquiry and our team will review it shortly.</p>
#
#         <p>We typically respond within <strong>24 hours</strong> during business days.</p>
#
#         <div style="background: #f7fafc; padding: 20px; border-radius: 8px; margin: 20px 0;">
#           <h3 style="color: #4a5568; margin-top: 0; font-size: 16px;">Your Inquiry Details:</h3>
#           <p style="margin: 5px 0;"><strong>Name:</strong> {data.name}</p>
#           <p style="margin: 5px 0;"><strong>Email:</strong> {data.email}</p>
#           <p style="margin: 5px 0;"><strong>Message:</strong></p>
#           <p style="margin: 5px 0; color: #4a5568;">{data.message}</p>
#         </div>
#
#         <p>In the meantime, feel free to explore our <a href="https://valvantadigital.co.za/services" style="color: #e8a598;">services</a> or check out our <a href="https://valvantadigital.co.za/portfolio" style="color: #e8a598;">portfolio</a>.</p>
#
#         <p>We look forward to helping your business grow online!</p>
#
#         <p style="margin-bottom: 0;">
#           Warm regards,<br>
#           <strong>The Valvanta Digital Team</strong>
#         </p>
#       </div>
#
#       <div style="background: #f7fafc; padding: 20px; text-align: center; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 10px 10px;">
#         <p style="margin: 0; color: #718096; font-size: 14px;">
#           Valvanta Digital | Digital Marketing for South African Businesses
#         </p>
#         <p style="margin: 10px 0 0 0; color: #a0aec0; font-size: 12px;">
#           <a href="https://valvantadigital.co.za" style="color: #a0aec0;">valvantadigital.co.za</a>
#         </p>
#       </div>
#     </body>
#     </html>
#   """
