import discord
from discord.ext import commands
from discord import app_commands
import json
from dotenv import load_dotenv
import os
import asyncio
import math
from datetime import datetime, timedelta
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
from supabase import create_client, Client

load_dotenv("cred.env")


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


VOTER_ROLE_ID = 1412935186219270144
TICKET_CATEGORY_ID = 1412937692156657787
TRANSCRIPT_CHANNEL_ID = 1412935735102668931
AM_ROLE = 1412932583724945471
SM_ROLE = 1412932413100920892
OBRC_MEMBER_NAME = "OBRC"
COMMISSIONER_ID = 1412932287217008670
POLL_DURATION_HOURS = 24
EVIDENCE_VOTE_DURATION_MINUTES = 1440

def get_credentials():
    creds_str = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_str:
        raise RuntimeError("GOOGLE_CREDENTIALS not found in environment.")
    try:
        creds_json = json.loads(creds_str)
        return creds_json
    except Exception as e:
        raise RuntimeError(f"Failed to load GOOGLE_CREDENTIALS: {e}")

def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(get_credentials(), scope)
    client = gspread.authorize(creds)
    return client

class EvidenceVoteView(discord.ui.View):
    def __init__(self, evidence_id, timeout_seconds):
        super().__init__(timeout=timeout_seconds)
        self.evidence_id = evidence_id
        self.voters = set()
    
    @discord.ui.button(label="Accept Evidence", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_evidence(self, interaction: discord.Interaction, button: discord.ui.Button):

        voter_role = discord.utils.get(interaction.guild.roles, id=VOTER_ROLE_ID)
        if not voter_role or voter_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You don't have permission to vote on evidence.", ephemeral=True)
            return
        
        if interaction.user.id in self.voters:
            await interaction.response.send_message("❌ You have already voted on this evidence.", ephemeral=True)
            return
        
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("✅ Your vote to accept this evidence has been recorded.", ephemeral=True)
    
    @discord.ui.button(label="Reject Evidence", style=discord.ButtonStyle.red, emoji="❌")
    async def reject_evidence(self, interaction: discord.Interaction, button: discord.ui.Button):

        voter_role = discord.utils.get(interaction.guild.roles, id=VOTER_ROLE_ID)
        if not voter_role or voter_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You don't have permission to vote on evidence.", ephemeral=True)
            return
        
        if interaction.user.id in self.voters:
            await interaction.response.send_message("❌ You have already voted on this evidence.", ephemeral=True)
            return
        
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("❌ Your vote to reject this evidence has been recorded.", ephemeral=True)
    
    async def on_timeout(self):

        for item in self.children:
            item.disabled = True

class AutoRoleManager:
    def __init__(self):

        self.BLACKLISTED_ROLE = "Blacklisted"
        self.COMPANY_BLACKLIST_OWNER_ROLE = "Company Blacklist (Owner)"
        self.COMPANY_BLACKLIST_PERSONNEL_ROLE = "Company Blacklist (Personnel)"
    
    async def check_and_assign_roles(self, member):
        try:
            guild = member.guild
            

            blacklisted_role = self._get_role(guild, self.BLACKLISTED_ROLE)
            company_owner_role = self._get_role(guild, self.COMPANY_BLACKLIST_OWNER_ROLE)
            company_personnel_role = self._get_role(guild, self.COMPANY_BLACKLIST_PERSONNEL_ROLE)
            
            if not blacklisted_role or not company_owner_role or not company_personnel_role:
                print(f"Warning: Some roles not found in guild {guild.name}")
                return False
            
            roles_to_add = []
            roles_to_remove = [blacklisted_role, company_owner_role, company_personnel_role]
            

            personal_record = await blacklist_manager.search_person(member.id)
            if personal_record and personal_record.get('list_type') == 'blacklist':
                roles_to_add.append(blacklisted_role)
                print(f"Found {member} in personal blacklist")
            

            company_roles = await self._check_company_blacklists(member)
            roles_to_add.extend(company_roles)
            

            roles_to_remove = [role for role in roles_to_remove if role not in roles_to_add]
            

            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Auto-role: Blacklist detection")
                role_names = [role.name for role in roles_to_add]
                print(f"Added roles to {member}: {', '.join(role_names)}")
            
            if roles_to_remove:

                roles_to_remove = [role for role in roles_to_remove if role in member.roles]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Auto-role: No longer in blacklist")
                    role_names = [role.name for role in roles_to_remove]
                    print(f"Removed roles from {member}: {', '.join(role_names)}")
            
            return True
            
        except Exception as e:
            print(f"Error checking roles for {member}: {e}")
            return False
    
    def _get_role(self, guild, role_name):
        return discord.utils.get(guild.roles, name=role_name)
    
    async def _check_company_blacklists(self, member):
        roles_to_add = []
        
        try:

            company_records = await blacklist_manager.get_all_records("blacklist_coo")
            
            member_id = str(member.id)
            member_mention = member.mention
            member_name = str(member).lower()
            member_display_name = member.display_name.lower()
            
            for record in company_records:

                owner_field = record.get('owner', '')
                if self._is_member_in_field(member_id, member_mention, member_name, member_display_name, owner_field):
                    owner_role = self._get_role(member.guild, self.COMPANY_BLACKLIST_OWNER_ROLE)
                    if owner_role and owner_role not in roles_to_add:
                        roles_to_add.append(owner_role)
                        print(f"Found {member} as owner in company blacklist: {record.get('company_name')}")
                

                personnel_field = record.get('personnel', '')
                if self._is_member_in_field(member_id, member_mention, member_name, member_display_name, personnel_field):
                    personnel_role = self._get_role(member.guild, self.COMPANY_BLACKLIST_PERSONNEL_ROLE)
                    if personnel_role and personnel_role not in roles_to_add:
                        roles_to_add.append(personnel_role)
                        print(f"Found {member} in personnel of company blacklist: {record.get('company_name')}")
                

                alts_field = record.get('alts', '')
                if self._is_member_in_field(member_id, member_mention, member_name, member_display_name, alts_field):
                    personnel_role = self._get_role(member.guild, self.COMPANY_BLACKLIST_PERSONNEL_ROLE)
                    if personnel_role and personnel_role not in roles_to_add:
                        roles_to_add.append(personnel_role)
                        print(f"Found {member} in alts of company blacklist: {record.get('company_name')}")
            
        except Exception as e:
            print(f"Error checking company blacklists for {member}: {e}")
        
        return roles_to_add
    
    def _is_member_in_field(self, member_id, member_mention, member_name, member_display_name, field_text):
        if not field_text:
            return False
        
        field_lower = field_text.lower()
        

        return any([
            member_id in field_text,
            member_mention in field_text,
            f"<@{member_id}>" in field_text,
            f"<@!{member_id}>" in field_text,
            member_name in field_lower,
            member_display_name in field_lower
        ])

class VotingTicketManager:
    def __init__(self):
        pass
    
    async def notify_voters(self, guild, ticket_type, target_name, ticket_channel):
        try:
            voter_role = discord.utils.get(guild.roles, id=VOTER_ROLE_ID)
            if not voter_role:
                print("Voter role not found for notifications")
                return
            
            action_text = "Add to" if ticket_type == "add" else "Remove from"
            if ticket_type == "add_company":
                action_text = "Add company to"
            elif ticket_type == "remove_company":
                action_text = "Remove company from"
            
            embed = discord.Embed(
                title="🗳️ New Vote Available",
                colour=discord.Colour.blue(),
                description=f"A new vote has been created: **{action_text} {target_name}**\n\n"
                            f"Please visit {ticket_channel.mention} to cast your vote.",
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Vote Details",
                value=f"**Action:** {action_text} Blacklist\n"
                        f"**Target:** {target_name}\n"
                        f"**Duration:** {POLL_DURATION_HOURS} hours",
                inline=False
            )
            
            successful_notifications = 0
            failed_notifications = 0
            
            for member in voter_role.members:
                try:
                    await member.send(embed=embed)
                    successful_notifications += 1

                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Failed to DM {member}: {e}")
                    failed_notifications += 1
            
            print(f"Voter notifications: {successful_notifications} successful, {failed_notifications} failed")
            
        except Exception as e:
            print(f"Error sending voter notifications: {e}")
    
    async def create_voting_ticket(self, guild, ticket_type, target_name, target_discord_id, target_nation_id, proposal_data, created_by):
        try:
            message = None
            category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)
            if not category:
                raise Exception("Ticket category not found")
            

            voter_role = discord.utils.get(guild.roles, id=VOTER_ROLE_ID)
            if not voter_role:
                raise Exception("Voter role not found")
            

            ticket_name = f"{ticket_type}-{target_name.lower().replace(' ', '-')}"
            

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                voter_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            
            ticket_channel = await category.create_text_channel(
                name=ticket_name,
                overwrites=overwrites
            )
            

            action_text = "Add to" if ticket_type == "add" else "Remove from"
            if ticket_type == "add_company":
                action_text = "Add company to"
            elif ticket_type == "remove_company":
                action_text = "Remove company from"
            
            color = discord.Colour.red() if "add" in ticket_type else discord.Colour.green()
            
            embed = discord.Embed(
                title=f"🗳️ Vote: {action_text} Blacklist",
                colour=color,
                description=f"**Target:** {target_name}\n**Proposed by:** {created_by.mention}",
                timestamp=datetime.utcnow()
            )
            
            if ticket_type in ["add", "add_company"]:
                data = json.loads(proposal_data)
                if ticket_type == "add":
                    embed.add_field(name="Discord ID", value=target_discord_id or "N/A", inline=True)
                    embed.add_field(name="Nation ID", value=target_nation_id or "N/A", inline=True)
                    embed.add_field(name="Possible Alts", value=data.get('possible_alts', 'None'), inline=True)
                elif ticket_type == "add_company":
                    embed.add_field(name="Owner", value=data.get('owner', 'N/A'), inline=True)
                    embed.add_field(name="Personnel", value=data.get('personnel', 'None'), inline=True)
                    embed.add_field(name="Alts", value=data.get('alts', 'None'), inline=True)
                
                embed.add_field(name="Reason", value=data['reason'], inline=False)
                
                if data.get('proof_urls'):
                    proof_urls = data['proof_urls'].split(', ')
                    proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls) if url])
                    embed.add_field(name="Evidence", value=proof_text, inline=False)
                

                embed.add_field(
                    name="📋 Note",
                    value="If this vote fails, the target will be added to the greylist for monitoring.",
                    inline=False
                )
            else:
                data = json.loads(proposal_data)

                if 'original_entry' in data:
                    original = data['original_entry']
                    message = f"**DO NOTE: IF THE APPEALING PARTY IS CAUGHT VOTING, THE CASE WILL BE IMMIDIATELY AND WITH NO WARNING BE THROWN**"
                    if ticket_type == "remove":
                        embed.add_field(name="Current Discord ID", value=original.get('discord_id', 'N/A'), inline=True)
                        embed.add_field(name="Current Nation ID", value=original.get('nation_id', 'N/A'), inline=True)
                        embed.add_field(name="Current Possible Alts", value=original.get('possible_alts', 'None'), inline=True)
                    elif ticket_type == "remove_company":
                        embed.add_field(name="Current Owner", value=original.get('owner', 'N/A'), inline=True)
                        embed.add_field(name="Current Personnel", value=original.get('personnel', 'None'), inline=True)
                        embed.add_field(name="Current Alts", value=original.get('alts', 'None'), inline=True)
                    
                    embed.add_field(name="Current Reason", value=original.get('reason', 'N/A'), inline=False)
                    
                    if original.get('proof_urls'):
                        proof_urls = original.get('proof_urls').split(', ')
                        proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls) if url])
                        embed.add_field(name="Current Evidence", value=proof_text, inline=False)
                

                is_appeal = str(created_by.id) == target_discord_id
                appeal_label = "Appeal Reason" if is_appeal else "Removal Reason"
                embed.add_field(name=appeal_label, value=data['reason'], inline=False)
                

                if is_appeal:
                    message = f"**DO NOTE: IF THE APPEALING PARTY IS CAUGHT VOTING, THE CASE WILL BE IMMIDIATELY AND WITH NO WARNING BE THROWN**"
                    embed.title = f"🗳️ Vote: Appeal by {target_name}"
                    embed.description = f"**Appellant:** {target_name}\n**Self-Appeal**"
                    embed.add_field(
                        name="⚠️ Appeal Note",
                        value="The appealing person's vote will not count towards the final result.",
                        inline=False
                    )

            
            embed.add_field(
                name="Voting Information",
                value=f"**Duration:** {POLL_DURATION_HOURS} hours\n**Required:** 2/3 majority to pass\n**Voters:** {voter_role.mention}",
                inline=False
            )
            

            await ticket_channel.send(f"{voter_role.mention}", embed=embed)
            

            poll_question = f"{action_text} {target_name}?"
            poll = discord.Poll(
                question=poll_question,
                duration=timedelta(hours=POLL_DURATION_HOURS)
            )
            poll.add_answer(text=f"Yes - {action_text}", emoji="✅")
            poll.add_answer(text="No - Keep current status", emoji="❌")
            

            poll_message = await ticket_channel.send(poll=poll)
            await poll_message.pin()
            

            expires_at = datetime.utcnow() + timedelta(hours=POLL_DURATION_HOURS)
            
            ticket_data = {
                "ticket_channel_id": str(ticket_channel.id),
                "poll_message_id": str(poll_message.id),
                "ticket_type": ticket_type,
                "target_discord_id": target_discord_id,
                "target_nation_id": target_nation_id,
                "target_name": target_name,
                "proposal_data": proposal_data,
                "created_by": str(created_by.id),
                "expires_at": expires_at.isoformat()
            }
            
            try:
                result = supabase.table("voting_tickets").insert(ticket_data).execute()
                print(f"Inserted ticket: {result}")
            except Exception as e:
                print(f"Error inserting ticket: {e}")
            

            await self.notify_voters(guild, ticket_type, target_name, ticket_channel)
            if message:
                await ticket_channel.send(message)

            
            return ticket_channel, poll_message
            
        except Exception as e:
            print(f"Error creating voting ticket: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    async def check_expired_polls(self, bot):
        try:

            current_time = datetime.utcnow().isoformat()
            result = supabase.table("voting_tickets").select("*").eq("status", "active").lt("expires_at", current_time).execute()
            
            expired_tickets = result.data if result.data else []
            
            for ticket_row in expired_tickets:

                channel = bot.get_channel(int(ticket_row['ticket_channel_id']))
                if channel:
                    await self._process_expired_ticket(bot, ticket_row)
                else:

                    print(f"Ticket channel {ticket_row['ticket_channel_id']} no longer exists, marking as completed")
                    supabase.table("voting_tickets").update({
                        "status": "completed",
                        "final_result": "channel_deleted"
                    }).eq("id", ticket_row['id']).execute()
            

            evidence_result = supabase.table("evidence_votes").select("*").eq("status", "active").lt("expires_at", current_time).execute()
            expired_evidence = evidence_result.data if evidence_result.data else []
            
            for evidence_row in expired_evidence:

                channel = bot.get_channel(int(evidence_row['ticket_channel_id']))
                if channel:
                    await self._process_expired_evidence(bot, evidence_row)
                else:

                    print(f"Evidence vote channel {evidence_row['ticket_channel_id']} no longer exists, marking as completed")
                    supabase.table("evidence_votes").update({
                        "status": "completed",
                        "final_result": "channel_deleted"
                    }).eq("id", evidence_row['id']).execute()
            
        except Exception as e:
            print(f"Error checking expired polls: {e}")
            import traceback
            traceback.print_exc()
    
    async def _process_expired_ticket(self, bot, ticket_row):
        try:
            channel = bot.get_channel(int(ticket_row['ticket_channel_id']))
            if not channel:
                print(f"Ticket channel {ticket_row['ticket_channel_id']} not found")
                supabase.table("voting_tickets").update({
                    "status": "completed",
                    "final_result": "channel_not_found"
                }).eq("id", ticket_row['id']).execute()
                return
            
            try:
                poll_message = await channel.fetch_message(int(ticket_row['poll_message_id']))
                if not poll_message or not poll_message.poll:
                    print(f"Poll message {ticket_row['poll_message_id']} not found or has no poll")
                    return
            except discord.NotFound:
                print(f"Poll message {ticket_row['poll_message_id']} was deleted")
                return

            poll = poll_message.poll
            yes_votes = 0
            no_votes = 0
            
            if poll.answers:
                if len(poll.answers) > 0:
                    yes_votes = poll.answers[0].vote_count
                if len(poll.answers) > 1:
                    no_votes = poll.answers[1].vote_count


            is_appeal = str(ticket_row['created_by']) == ticket_row['target_discord_id']
            if is_appeal:
                print(f"DEBUG: Processing appeal for {ticket_row['target_name']} (ID: {ticket_row['target_discord_id']})")
                
                try:
                    appealing_user_id = int(ticket_row['target_discord_id'])
                    

                    for answer_index, answer in enumerate(poll.answers):
                        try:

                            users = [user async for user in answer.users()]
                            user_ids = [user.id for user in users]
                            
                            if appealing_user_id in user_ids:
                                print(f"DEBUG: Found appealing user's vote in answer {answer_index}: {answer.text}")
                                

                                if answer_index == 0:
                                    yes_votes = max(0, yes_votes - 1)
                                    print(f"DEBUG: Removed yes vote, new count: {yes_votes}")
                                elif answer_index == 1:
                                    no_votes = max(0, no_votes - 1)
                                    print(f"DEBUG: Removed no vote, new count: {no_votes}")
                                break
                        except Exception as e:
                            print(f"Error checking users for answer {answer_index}: {e}")

                            continue
                            
                except Exception as e:
                    print(f"Error checking appeal vote exclusion: {e}")
            
            total_votes = yes_votes + no_votes
            

            passed = False
            if total_votes > 0:
                yes_percentage = yes_votes / total_votes
                passed = yes_percentage >= (2/3)
            
            result_text = "PASSED" if passed else "FAILED"
            result_color = discord.Colour.green() if passed else discord.Colour.red()
            

            result_embed = discord.Embed(
                title=f"🗳️ Vote Result: {result_text}",
                colour=result_color,
                description=f"**Votes:** ✅ {yes_votes} | ❌ {no_votes}\n**Total:** {total_votes}",
                timestamp=datetime.utcnow()
            )
            

            if is_appeal:
                result_embed.add_field(
                    name="ℹ️ Appeal Vote Processing",
                    value="The appealing person's vote was excluded from the final count as per appeal rules.",
                    inline=False
                )
            

            action_taken = False
            if passed:
                if ticket_row['ticket_type'] == "add":
                    action_taken = await self._execute_add_action(ticket_row['target_discord_id'], ticket_row['target_nation_id'], ticket_row['proposal_data'], ticket_row['created_by'])
                elif ticket_row['ticket_type'] == "remove":
                    action_taken = await self._execute_remove_action(ticket_row['target_discord_id'], ticket_row['proposal_data'], ticket_row['created_by'])
                elif ticket_row['ticket_type'] == "add_company":
                    action_taken = await self._execute_add_company_action(ticket_row['proposal_data'], ticket_row['created_by'])
                elif ticket_row['ticket_type'] == "remove_company":
                    action_taken = await self._execute_remove_company_action(ticket_row['target_name'], ticket_row['proposal_data'], ticket_row['created_by'])
            else:

                if ticket_row['ticket_type'] in ["add", "add_company"]:
                    await self._add_to_greylist_on_failure(ticket_row, ticket_row['created_by'])
                    result_embed.add_field(
                        name="📋 Added to Greylist",
                        value="Since the blacklist vote failed, the target has been added to the greylist for monitoring.",
                        inline=False
                    )
            
            if passed and action_taken:
                action_text = "added to" if "add" in ticket_row['ticket_type'] else "removed from"
                result_embed.add_field(
                    name="✅ Action Completed",
                    value=f"{ticket_row['target_name']} has been {action_text} the blacklist.",
                    inline=False
                )
            elif passed and not action_taken:
                result_embed.add_field(
                    name="❌ Action Failed",
                    value="Vote passed but failed to execute the action.",
                    inline=False
                )
            
            await channel.send(embed=result_embed)
            

            await self._create_transcript(bot, channel, ticket_row['ticket_type'], ticket_row['target_name'], result_text, yes_votes, no_votes)
            

            supabase.table("voting_tickets").update({
                "status": "completed",
                "final_result": f"{result_text}:{yes_votes}:{no_votes}"
            }).eq("id", ticket_row['id']).execute()
            

            await asyncio.sleep(30)
            try:
                await channel.delete()
                print(f"Successfully deleted ticket channel {channel.name}")
            except Exception as e:
                print(f"Error deleting ticket channel: {e}")
            
        except Exception as e:
            print(f"Error processing expired ticket: {e}")
            import traceback
            traceback.print_exc()
    
    async def _add_to_greylist_on_failure(self, ticket_row, created_by):
        try:
            data = json.loads(ticket_row['proposal_data'])
            
            if ticket_row['ticket_type'] == "add":
                greylist_data = {
                    "discord_id": ticket_row['target_discord_id'] or '',
                    "discord_name": data.get('discord_name', ticket_row['target_name']),
                    "nation_id": ticket_row['target_nation_id'] or '',
                    "nation_url": f"https://www.politicsandwar.com/nation/id={ticket_row['target_nation_id']}" if ticket_row['target_nation_id'] else '',
                    "possible_alts": data.get('possible_alts', 'None'),
                    "reason": f"Failed blacklist vote - Original reason: {data['reason']}",
                    "proof_urls": data.get('proof_urls', ''),
                    "added_by": f"Vote initiated by {created_by}"
                }
                
                supabase.table("greylist").insert(greylist_data).execute()
                print(f"Added {ticket_row['target_name']} to greylist")
                
            elif ticket_row['ticket_type'] == "add_company":
                greylist_data = {
                    "company_name": ticket_row['target_name'],
                    "owner": data.get('owner', ''),
                    "personnel": data.get('personnel', ''),
                    "alts": data.get('alts', ''),
                    "reason": f"Failed blacklist vote - Original reason: {data['reason']}",
                    "proof_urls": data.get('proof_urls', ''),
                    "added_by": f"Vote initiated by {created_by}"
                }
                
                supabase.table("greylist_coo").insert(greylist_data).execute()
                print(f"Added company {ticket_row['target_name']} to greylist")
                
        except Exception as e:
            print(f"Error adding to greylist: {e}")
            import traceback
            traceback.print_exc()
    
    async def _process_expired_evidence(self, bot, evidence_row):
        try:
            channel = bot.get_channel(int(evidence_row['ticket_channel_id']))
            if not channel:
                print(f"Evidence vote channel {evidence_row['ticket_channel_id']} not found")
                supabase.table("evidence_votes").update({
                    "status": "completed",
                    "final_result": "channel_not_found"
                }).eq("id", evidence_row['id']).execute()
                return
            
            try:
                message = await channel.fetch_message(int(evidence_row['message_id']))
                

                accept_votes = 0
                reject_votes = 0
                
                if message.poll:

                    for answer in message.poll.answers:
                        if "accept" in answer.text.lower() or "✅" in str(answer.emoji):
                            accept_votes = answer.vote_count
                        elif "reject" in answer.text.lower() or "❌" in str(answer.emoji):
                            reject_votes = answer.vote_count
                

                if accept_votes > reject_votes:
                    final_result = "accepted"
                    result_color = discord.Colour.green()
                    result_text = f"**✅ ACCEPTED** ({accept_votes} accept, {reject_votes} reject)"
                elif reject_votes > accept_votes:
                    final_result = "rejected"
                    result_color = discord.Colour.red()
                    result_text = f"**❌ REJECTED** ({accept_votes} accept, {reject_votes} reject)"
                else:
                    final_result = "tied"
                    result_color = discord.Colour.orange()
                    result_text = f"**🤝 TIED** ({accept_votes} accept, {reject_votes} reject)"
                
                result_embed = discord.Embed(
                    title="📎 Evidence Vote Results",
                    colour=result_color,
                    description=f"**Evidence:** [View Evidence]({evidence_row['evidence_url']})\n"
                            f"**Description:** {evidence_row.get('evidence_description', 'No description')}\n"
                            f"**Submitted by:** <@{evidence_row['submitted_by']}>",
                    timestamp=datetime.utcnow()
                )
                
                result_embed.add_field(
                    name="Final Result",
                    value=result_text,
                    inline=False
                )
                
                await channel.send(embed=result_embed)
                

                supabase.table("evidence_votes").update({
                    "status": "completed",
                    "final_result": final_result
                }).eq("id", evidence_row['id']).execute()
                
            except discord.NotFound:
                print(f"Evidence vote message {evidence_row['message_id']} not found")
                supabase.table("evidence_votes").update({
                    "status": "completed",
                    "final_result": "message_not_found"
                }).eq("id", evidence_row['id']).execute()
                
        except Exception as e:
            print(f"Error processing expired evidence: {e}")
    
    async def _execute_add_action(self, target_discord_id, target_nation_id, proposal_data, created_by):
        try:
            data = json.loads(proposal_data)
            

            blacklist_manager = BlacklistManager()
            if target_discord_id:
                existing_record = await blacklist_manager.search_person(target_discord_id)
                if existing_record:
                    return False
            

            if target_discord_id:
                await blacklist_manager.remove_from_greylist(target_discord_id)
            

            add_data = {
                'discord_id': target_discord_id or '',
                'discord_name': data.get('discord_name', ''),
                'nation_id': target_nation_id or '',
                'nation_url': f"https://www.politicsandwar.com/nation/id={target_nation_id}" if target_nation_id else '',
                'possible_alts': data.get('possible_alts', 'None'),
                'reason': data['reason'],
                'proof_urls': data.get('proof_urls', ''),
                'added_by': f"Vote initiated by {created_by}"
            }
            
            return await blacklist_manager.add_person(add_data)
            
        except Exception as e:
            print(f"Error executing add action: {e}")
            return False
    
    async def _execute_remove_action(self, target_discord_id, proposal_data, created_by):
        try:
            data = json.loads(proposal_data)
            original_entry = data.get('original_entry')
            
            if not original_entry:
                print("ERROR: No original entry found in proposal data")
                return False
            

            discord_id_to_remove = target_discord_id
            if not discord_id_to_remove or discord_id_to_remove == "":
                discord_id_to_remove = original_entry.get('discord_id')
            
            if not discord_id_to_remove:
                print("ERROR: No Discord ID found to remove")
                return False
            
            print(f"DEBUG: Attempting to remove Discord ID: {discord_id_to_remove}")
            
            blacklist_manager = BlacklistManager()
            removed_record = await blacklist_manager.remove_person(discord_id_to_remove)
            
            print(f"DEBUG: Removal result: {removed_record is not None}")
            return removed_record is not None
            
        except Exception as e:
            print(f"Error executing remove action: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _execute_add_company_action(self, proposal_data, created_by):
        try:
            data = json.loads(proposal_data)
            

            blacklist_manager = BlacklistManager()
            existing_record = await blacklist_manager.search_company(data['company_name'])
            if existing_record:
                return False
            

            await blacklist_manager.remove_company_from_greylist(data['company_name'])
            

            add_data = {
                'company_name': data['company_name'],
                'owner': data.get('owner', ''),
                'personnel': data.get('personnel', ''),
                'alts': data.get('alts', ''),
                'reason': data['reason'],
                'proof_urls': data.get('proof_urls', ''),
                'added_by': f"Vote initiated by {created_by}"
            }
            
            return await blacklist_manager.add_company(add_data)
            
        except Exception as e:
            print(f"Error executing add company action: {e}")
            return False
    
    async def _execute_remove_company_action(self, company_name, proposal_data, created_by):
        try:
            blacklist_manager = BlacklistManager()
            removed_record = await blacklist_manager.remove_company(company_name)
            
            return removed_record is not None
            
        except Exception as e:
            print(f"Error executing remove company action: {e}")
            return False
    
    async def _create_transcript(self, bot, channel, ticket_type, target_name, result, yes_votes, no_votes):
        try:
            transcript_channel = bot.get_channel(TRANSCRIPT_CHANNEL_ID)
            if not transcript_channel:
                print("Transcript channel not found")
                return
            

            messages = []
            async for message in channel.history(limit=None, oldest_first=True):
                timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
                author = str(message.author)
                content = message.content or "[No content]"
                

                if message.embeds:
                    content += f" [Embeds: {len(message.embeds)}]"
                

                if message.poll:
                    content += f" [Poll: {message.poll.question}]"
                
                messages.append(f"[{timestamp}] {author}: {content}")
            

            transcript_content = f"""VOTING TICKET TRANSCRIPT
======================
Channel:
Type: {ticket_type.upper()}
Target: {target_name}
Result: {result}
Votes: ✅ {yes_votes} | ❌ {no_votes}
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

MESSAGES
========
""" + "\n".join(messages)
            

            transcript_file = discord.File(
                io.StringIO(transcript_content),
                filename=f"transcript_{channel.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            transcript_embed = discord.Embed(
                title="📄 Voting Ticket Transcript",
                colour=discord.Colour.blue(),
                description=f"**Channel:**"
                           f"**Type:** {ticket_type.upper()}\n"
                           f"**Target:** {target_name}\n"
                           f"**Result:** {result}\n"
                           f"**Votes:** ✅ {yes_votes} | ❌ {no_votes}",
                timestamp=datetime.utcnow()
            )
            
            await transcript_channel.send(embed=transcript_embed, file=transcript_file)
            
        except Exception as e:
            print(f"Error creating transcript: {e}")

class BlacklistManager:
    def __init__(self):
        pass
    
    async def search_person(self, discord_id):
        try:
            search_id = str(discord_id)
            print(f"DEBUG: Searching for Discord ID: {search_id}")
            

            result = supabase.table("blacklist").select("*").eq("discord_id", search_id).execute()
            
            if result.data:
                record = result.data[0]
                record['list_type'] = 'blacklist'
                return record
            

            all_records = supabase.table("blacklist").select("*").execute()
            
            import re
            for record in all_records.data:
                possible_alts = record.get('possible_alts', '')
                if possible_alts:
                    alt_ids = re.findall(r'<@(\d+)>', possible_alts)
                    alt_ids.extend(re.findall(r'\b(\d{17,19})\b', possible_alts))
                    
                    if search_id in alt_ids:
                        record['list_type'] = 'blacklist'
                        return record
            

            result = supabase.table("greylist").select("*").eq("discord_id", search_id).execute()
            
            if result.data:
                record = result.data[0]
                record['list_type'] = 'greylist'
                return record
            

            all_grey_records = supabase.table("greylist").select("*").execute()
            
            for record in all_grey_records.data:
                possible_alts = record.get('possible_alts', '')
                if possible_alts:
                    alt_ids = re.findall(r'<@(\d+)>', possible_alts)
                    alt_ids.extend(re.findall(r'\b(\d{17,19})\b', possible_alts))
                    
                    if search_id in alt_ids:
                        record['list_type'] = 'greylist'
                        return record
            
            return None
            
        except Exception as e:
            print(f"Error searching person: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def search_by_nation(self, search_term):
        try:
            nation_id = search_term
            if "politicsandwar.com/nation/id=" in search_term:
                import re
                match = re.search(r'id=(\d+)', search_term)
                if match:
                    nation_id = match.group(1)
            

            result = supabase.table("blacklist").select("*").eq("nation_id", nation_id).execute()
            if result.data:
                record = result.data[0]
                record['list_type'] = 'blacklist'
                return record
            

            result = supabase.table("greylist").select("*").eq("nation_id", nation_id).execute()
            if result.data:
                record = result.data[0]
                record['list_type'] = 'greylist'
                return record
            
            return None
            
        except Exception as e:
            print(f"Error searching by nation: {e}")
            return None
    
    async def search_company(self, company_name):
        try:

            result = supabase.table("blacklist_coo").select("*").ilike("company_name", f"%{company_name}%").execute()
            if result.data:
                record = result.data[0]
                record['list_type'] = 'blacklist'
                return record
            

            result = supabase.table("greylist_coo").select("*").ilike("company_name", f"%{company_name}%").execute()
            if result.data:
                record = result.data[0]
                record['list_type'] = 'greylist'
                return record
            
            return None
            
        except Exception as e:
            print(f"Error searching company: {e}")
            return None
    
    async def add_person(self, data):
        try:
            result = supabase.table("blacklist").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error adding person: {e}")
            return False
    
    async def add_company(self, data):
        try:
            result = supabase.table("blacklist_coo").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error adding company: {e}")
            return False
    
    async def remove_person(self, discord_id):
        try:
            search_id = str(discord_id)
            

            result = supabase.table("blacklist").select("*").eq("discord_id", search_id).execute()
            
            if result.data:
                record = result.data[0]
                supabase.table("blacklist").delete().eq("discord_id", search_id).execute()
                return record
            

            all_records = supabase.table("blacklist").select("*").execute()
            
            import re
            for record in all_records.data:
                possible_alts = record.get('possible_alts', '')
                if possible_alts:
                    alt_ids = re.findall(r'<@(\d+)>', possible_alts)
                    alt_ids.extend(re.findall(r'\b(\d{17,19})\b', possible_alts))
                    
                    if search_id in alt_ids:
                        supabase.table("blacklist").delete().eq("id", record['id']).execute()
                        return record
            
            return None
            
        except Exception as e:
            print(f"Error removing person: {e}")
            return None
    
    async def remove_company(self, company_name):
        try:
            result = supabase.table("blacklist_coo").select("*").ilike("company_name", f"%{company_name}%").execute()
            
            if result.data:
                record = result.data[0]
                supabase.table("blacklist_coo").delete().eq("id", record['id']).execute()
                return record
            
            return None
            
        except Exception as e:
            print(f"Error removing company: {e}")
            return None
    
    async def remove_from_greylist(self, discord_id):
        try:
            search_id = str(discord_id)
            supabase.table("greylist").delete().eq("discord_id", search_id).execute()
            print(f"Removed {search_id} from greylist")
        except Exception as e:
            print(f"Error removing from greylist: {e}")
    
    async def remove_company_from_greylist(self, company_name):
        try:
            supabase.table("greylist_coo").delete().ilike("company_name", f"%{company_name}%").execute()
            print(f"Removed {company_name} from company greylist")
        except Exception as e:
            print(f"Error removing company from greylist: {e}")
    
    async def edit_person(self, discord_id, field, new_value, modified_by, edit_mode="replace", list_type="both"):
        try:
            search_id = str(discord_id)
            

            valid_fields = {
                'discord_name': 'discord_name',
                'nation_id': 'nation_id', 
                'nation_url': 'nation_url',
                'possible_alts': 'possible_alts',
                'reason': 'reason',
                'proof_urls': 'proof_urls'
            }
            
            if field not in valid_fields:
                return False
            
            db_field = valid_fields[field]
            current_time = datetime.now()
            
            results = []
            

            if list_type in ["both", "blacklist"]:
                result = await self._edit_in_table("blacklist", search_id, db_field, new_value, modified_by, edit_mode, current_time)
                if result:
                    results.append(("blacklist", result))
            

            if list_type in ["both", "greylist"]:
                result = await self._edit_in_table("greylist", search_id, db_field, new_value, modified_by, edit_mode, current_time)
                if result:
                    results.append(("greylist", result))
            
            return results if results else False
            
        except Exception as e:
            print(f"Error editing person: {e}")
            return False
    
    async def edit_company(self, company_name, field, new_value, modified_by, edit_mode="replace", list_type="both"):
        try:

            valid_fields = {
                'company_name': 'company_name',
                'owner': 'owner',
                'personnel': 'personnel',
                'alts': 'alts',
                'reason': 'reason',
                'proof_urls': 'proof_urls'
            }
            
            if field not in valid_fields:
                return False
            
            db_field = valid_fields[field]
            current_time = datetime.now()
            
            results = []
            

            if list_type in ["both", "blacklist"]:
                result = await self._edit_company_in_table("blacklist_coo", company_name, db_field, new_value, modified_by, edit_mode, current_time)
                if result:
                    results.append(("blacklist", result))
            

            if list_type in ["both", "greylist"]:
                result = await self._edit_company_in_table("greylist_coo", company_name, db_field, new_value, modified_by, edit_mode, current_time)
                if result:
                    results.append(("greylist", result))
            
            return results if results else False
            
        except Exception as e:
            print(f"Error editing company: {e}")
            return False
    
    async def _edit_in_table(self, table_name, discord_id, field, new_value, modified_by, edit_mode, current_time):
        try:

            result = supabase.table(table_name).select("*").eq("discord_id", discord_id).execute()
            
            
            if not result.data:

                all_records = supabase.table(table_name).select("*").execute()
                import re
                for record in all_records.data:
                    possible_alts = record.get('possible_alts', '')
                    if possible_alts:
                        alt_ids = re.findall(r'<@(\d+)>', possible_alts)
                        alt_ids.extend(re.findall(r'\b(\d{17,19})\b', possible_alts))
                        
                        if discord_id in alt_ids:
                            result.data = [record]
                            break
            
            if not result.data:
                return None
            
            record = result.data[0]
            current_value = record.get(field, "") or ""
            

            if edit_mode == "append" and current_value and current_value.strip():
                if field == "proof_urls":
                    final_value = f"{current_value}, {new_value}"
                elif field == "possible_alts":
                    final_value = f"{current_value}, {new_value}"
                elif field == "reason":
                    final_value = f"{current_value} | {new_value}"
                else:
                    final_value = f"{current_value} {new_value}"
            else:
                final_value = new_value
            

            update_data = {
                field: final_value,
                "last_modified": current_time.isoformat(),
                "modified_by": modified_by
            }
            
            supabase.table(table_name).update(update_data).eq("id", record['id']).execute()
            

            updated_result = supabase.table(table_name).select("*").eq("id", record['id']).execute()
            return updated_result.data[0] if updated_result.data else None
            
        except Exception as e:
            print(f"Error editing in table {table_name}: {e}")
            return None
    
    async def _edit_company_in_table(self, table_name, company_name, field, new_value, modified_by, edit_mode, current_time):
        try:

            result = supabase.table(table_name).select("*").ilike("company_name", f"%{company_name}%").execute()
            
            if not result.data:
                return None
            
            record = result.data[0]
            current_value = record.get(field, "") or ""
            

            if edit_mode == "append" and current_value and current_value.strip():
                if field == "proof_urls":
                    final_value = f"{current_value}, {new_value}"
                elif field == "alts":
                    final_value = f"{current_value}, {new_value}"
                elif field == "reason":
                    final_value = f"{current_value} | {new_value}"
                else:
                    final_value = f"{current_value} {new_value}"
            else:
                final_value = new_value
            

            update_data = {
                field: final_value,
                "last_modified": current_time.isoformat(),
                "modified_by": modified_by
            }
            
            supabase.table(table_name).update(update_data).eq("id", record['id']).execute()
            

            updated_result = supabase.table(table_name).select("*").eq("id", record['id']).execute()
            return updated_result.data[0] if updated_result.data else None
            
        except Exception as e:
            print(f"Error editing company in table {table_name}: {e}")
            return None
    
    async def edit_multiple_people(self, discord_ids, field, new_value, modified_by, edit_mode="replace", list_type="both"):
        results = []
        for discord_id in discord_ids:
            result = await self.edit_person(discord_id, field, new_value, modified_by, edit_mode, list_type)
            results.append((discord_id, result))
        return results
    
    async def get_all_records(self, list_type="blacklist"):
        try:
            if list_type == "blacklist":
                result = supabase.table("blacklist").select("*").order("date_added", desc=True).execute()
            elif list_type == "greylist":
                result = supabase.table("greylist").select("*").order("date_added", desc=True).execute()
            elif list_type == "blacklist_coo":
                result = supabase.table("blacklist_coo").select("*").order("date_added", desc=True).execute()
            elif list_type == "greylist_coo":
                result = supabase.table("greylist_coo").select("*").order("date_added", desc=True).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            print(f"Error getting all records: {e}")
            return []


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="$", intents=intents)

blacklist_manager = BlacklistManager()
voting_manager = VotingTicketManager()
auto_role_manager = AutoRoleManager()





@bot.tree.command(name="search_list", description="Search the blacklist and greylist")
@app_commands.describe(name="The member to check")
async def search_list(interaction: discord.Interaction, name: discord.Member):
    await interaction.response.defer()
    if not (any(role.name == OBRC_MEMBER_NAME for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)
    
    record = await blacklist_manager.search_person(name.id)
    
    if record:
        list_type = record.get('list_type', 'blacklist')
        
        if list_type == 'blacklist':
            title = "🚨 Blacklist Entry Found"
            color = discord.Colour.red()
        else:
            title = "⚠️ Greylist Entry Found"
            color = discord.Colour.orange()
        
        desc = (
            f"**Name:** {name.mention}\n"
            f"**List:** {list_type.title()}\n"
            f"**Nation URL:** [Politics & War]({record.get('nation_url', 'N/A')})\n"
            f"**Possible Alts:** {record.get('possible_alts', 'None')}\n"
            f"**Reason:** {record.get('reason', 'N/A')}\n"
            f"**Date Added:** {record.get('date_added', 'N/A')}\n"
            f"**Added By:** {record.get('added_by', 'N/A')}"
        )
        
        if record.get('last_modified'):
            desc += f"\n**Last Modified:** {record.get('last_modified', 'N/A')}\n**Modified By:** {record.get('modified_by', 'N/A')}"
        
        embed = discord.Embed(
            title=title,
            colour=color,
            description=desc
        )
        
        if record.get('proof_urls'):
            proof_urls = record.get('proof_urls').split(', ')
            proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls) if url])
            if proof_text:
                embed.add_field(name="Proof", value=proof_text, inline=False)
    else:
        embed = discord.Embed(
            title="✅ All Clear",
            colour=discord.Colour.green(),
            description=f"**{name.mention}** is not found in the blacklist or greylist."
        )
    
    await interaction.followup.send(embed=embed)



@bot.tree.command(name="propose_add_company", description="Propose adding a company to the blacklist (creates voting ticket)")
async def propose_add_company(
    interaction: discord.Interaction,
    company_name: str,
    owner: str,
    reason: str,
    proof: discord.Attachment,
    personnel: str = None,
    alts: str = None,
    proof2: discord.Attachment = None,
    proof3: discord.Attachment = None
):
    await interaction.response.defer(ephemeral=True)
    if not (any(role.id == COMMISSIONER_ID for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)
    
    if not company_name or not owner or not reason or not proof:
        embed = discord.Embed(
            title="❌ Missing Required Fields",
            colour=discord.Colour.red(),
            description="Company name, owner, reason, and proof are all required fields."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    existing_record = await blacklist_manager.search_company(company_name)
    if existing_record:
        list_type = existing_record.get('list_type', 'blacklist')
        embed = discord.Embed(
            title="❌ Already Exists",
            colour=discord.Colour.orange(),
            description=f"Company **{company_name}** is already in the {list_type}."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    proof_urls = [proof.url]
    if proof2:
        proof_urls.append(proof2.url)
    if proof3:
        proof_urls.append(proof3.url)
    

    proposal_data = {
        'company_name': company_name,
        'owner': owner,
        'personnel': personnel or 'None',
        'alts': alts or 'None',
        'reason': reason,
        'proof_urls': ', '.join(proof_urls)
    }
    

    ticket_channel, poll_message = await voting_manager.create_voting_ticket(
        interaction.guild,
        "add_company",
        company_name,
        None,
        None,
        json.dumps(proposal_data),
        interaction.user
    )
    
    if ticket_channel and poll_message:
        embed = discord.Embed(
            title="✅ Company Voting Ticket Created",
            colour=discord.Colour.blue(),
            description=f"Created voting ticket for adding company **{company_name}** to blacklist.\n\n"
                       f"**Channel:** {ticket_channel.mention}\n"
                       f"**Duration:** {POLL_DURATION_HOURS} hours\n"
                       f"**Required:** 2/3 majority to pass\n"
                       f"**Note:** If vote fails, company will be added to greylist."
        )
    else:
        embed = discord.Embed(
            title="❌ Error",
            colour=discord.Colour.red(),
            description="Failed to create voting ticket. Please try again."
        )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="appeal_company", description="Appeal a company blacklist entry (if you're the owner)")
async def appeal_company(
    interaction: discord.Interaction,
    company_name: str,
    reason: str
):
    await interaction.response.defer(ephemeral=True)
    
    if not company_name or not reason:
        embed = discord.Embed(
            title="❌ Missing Required Fields",
            colour=discord.Colour.red(),
            description="Company name and appeal reason are required fields."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    existing_record = await blacklist_manager.search_company(company_name)
    if not existing_record:
        embed = discord.Embed(
            title="❌ Company Not Found",
            colour=discord.Colour.orange(),
            description=f"Company **{company_name}** is not found in the blacklist or greylist."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if existing_record.get('list_type') != 'blacklist':
        embed = discord.Embed(
            title="❌ Not Blacklisted",
            colour=discord.Colour.orange(),
            description=f"Company **{company_name}** is only in the greylist. Appeals are only for blacklisted companies."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    company_owner = existing_record.get('owner', '').lower()
    user_name = str(interaction.user).lower()
    user_display_name = interaction.user.display_name.lower()
    user_id = str(interaction.user.id)
    

    is_owner = (
        user_name in company_owner or 
        user_display_name in company_owner or 
        user_id in company_owner or
        f"<@{user_id}>" in existing_record.get('owner', '')
    )
    
    if not is_owner:
        embed = discord.Embed(
            title="❌ Not Authorized",
            colour=discord.Colour.red(),
            description=f"You don't appear to be listed as the owner of **{company_name}**. Only company owners can appeal their own blacklist entries.\n\n"
                       f"**Current Owner Listed:** {existing_record.get('owner', 'N/A')}\n"
                       f"**Your Identity:** {interaction.user.mention}\n\n"
                       f"If you believe this is an error, please contact an administrator."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    proposal_data = {
        'reason': f"Company appeal by {interaction.user}: {reason}",
        'original_entry': existing_record,
        'is_company_appeal': True
    }
    

    ticket_channel, poll_message = await voting_manager.create_voting_ticket(
        interaction.guild,
        "remove_company",
        company_name,
        None,
        None,
        json.dumps(proposal_data),
        interaction.user
    )
    
    if ticket_channel and poll_message:
        embed = discord.Embed(
            title="✅ Company Appeal Submitted",
            colour=discord.Colour.blue(),
            description=f"Your appeal for company **{company_name}** has been submitted for voting.\n\n"
                       f"**Channel:** {ticket_channel.mention}\n"
                       f"**Duration:** {POLL_DURATION_HOURS} hours\n"
                       f"**Required:** 2/3 majority to approve your appeal"
        )
    else:
        embed = discord.Embed(
            title="❌ Error",
            colour=discord.Colour.red(),
            description="Failed to create appeal voting ticket. Please check with administrators."
        )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="search_nation", description="Search the blacklist and greylist by nation ID or URL")
@app_commands.describe(nation="Nation ID (e.g., 680627) or URL (e.g., politicsandwar.com/nation/id=680627)")
async def search_nation(interaction: discord.Interaction, nation: str):
    await interaction.response.defer()
    if not (any(role.name == OBRC_MEMBER_NAME for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)
    
    record = await blacklist_manager.search_by_nation(nation)
    
    if record:
        list_type = record.get('list_type', 'blacklist')
        
        if list_type == 'blacklist':
            title = "🚨 Blacklist Entry Found"
            color = discord.Colour.red()
        else:
            title = "⚠️ Greylist Entry Found"
            color = discord.Colour.orange()
        
        discord_user = None
        discord_id = record.get('discord_id')
        if discord_id:
            try:
                discord_user = await bot.fetch_user(int(discord_id))
            except:
                pass
        
        user_mention = discord_user.mention if discord_user else f"<@{discord_id}>"
        
        desc = (
            f"**Discord User:** {user_mention}\n"
            f"**List:** {list_type.title()}\n"
            f"**Nation URL:** [Politics & War]({record.get('nation_url', 'N/A')})\n"
            f"**Possible Alts:** {record.get('possible_alts', 'None')}\n"
            f"**Reason:** {record.get('reason', 'N/A')}\n"
            f"**Date Added:** {record.get('date_added', 'N/A')}\n"
            f"**Added By:** {record.get('added_by', 'N/A')}"
        )
        
        if record.get('last_modified'):
            desc += f"\n**Last Modified:** {record.get('last_modified', 'N/A')}\n**Modified By:** {record.get('modified_by', 'N/A')}"
        
        embed = discord.Embed(
            title=title,
            colour=color,
            description=desc
        )
        
        if record.get('proof_urls'):
            proof_urls = record.get('proof_urls').split(', ')
            proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls) if url])
            if proof_text:
                embed.add_field(name="Proof", value=proof_text, inline=False)
    else:
        embed = discord.Embed(
            title="✅ All Clear",
            colour=discord.Colour.green(),
            description=f"**Nation {nation}** is not found in the blacklist or greylist."
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="propose_add", description="Propose adding a person to the blacklist (creates voting ticket)")
async def propose_add(
    interaction: discord.Interaction,
    name: str,
    id: str,
    nation_id: str = None,
    proof: discord.Attachment = None,
    reason: str = None,
    proof2: discord.Attachment = None,
    proof3: discord.Attachment = None,
    pos_alts: str = None
):
    await interaction.response.defer(ephemeral=True)
    if not (any(role.id == COMMISSIONER_ID for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)

    if not name and not nation_id:
        embed = discord.Embed(
            title="❌ Invalid Input",
            colour=discord.Colour.red(),
            description="You must provide either a Discord member or a Nation ID."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if not proof or not reason:
        embed = discord.Embed(
            title="❌ Missing Required Fields",
            colour=discord.Colour.red(),
            description="Both `proof` and `reason` are required."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    target_discord_id = str(id) if name else None
    target_nation_id = nation_id
    target_name = str(name) if name else f"Nation {nation_id}"
    

    if name:
        existing_record = await blacklist_manager.search_person(name.id)
        if existing_record:
            list_type = existing_record.get('list_type', 'blacklist')
            embed = discord.Embed(
                title="❌ Already Exists",
                colour=discord.Colour.orange(),
                description=f"**{name.mention}** is already in the {list_type}."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    

    proof_urls = [proof.url]
    if proof2:
        proof_urls.append(proof2.url)
    if proof3:
        proof_urls.append(proof3.url)
    

    proposal_data = {
        'discord_name': str(name) if name else '',
        'reason': reason,
        'possible_alts': pos_alts or 'None',
        'proof_urls': ', '.join(proof_urls)
    }
    

    ticket_channel, poll_message = await voting_manager.create_voting_ticket(
        interaction.guild,
        "add",
        target_name,
        target_discord_id,
        target_nation_id,
        json.dumps(proposal_data),
        interaction.user
    )
    
    if ticket_channel and poll_message:
        embed = discord.Embed(
            title="✅ Voting Ticket Created",
            colour=discord.Colour.blue(),
            description=f"Created voting ticket for adding **{target_name}** to blacklist.\n\n"
                       f"**Channel:** {ticket_channel.mention}\n"
                       f"**Duration:** {POLL_DURATION_HOURS} hours\n"
                       f"**Required:** 2/3 majority to pass\n"
                       f"**Note:** If vote fails, target will be added to greylist."
        )
    else:
        embed = discord.Embed(
            title="❌ Error",
            colour=discord.Colour.red(),
            description="Failed to create voting ticket. Please try again."
        )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="appeal", description="Appeal your own blacklist entry")
async def appeal(
    interaction: discord.Interaction,
    reason: str
):
    await interaction.response.defer(ephemeral=True)

    existing_record = None
    target_name = str(interaction.user)
    target_discord_id = str(interaction.user.id)
    target_nation_id = ""

    try:
        existing_record = await blacklist_manager.search_person(interaction.user.id)
    except Exception as e:
        embed = discord.Embed(
            title="❌ Search Error",
            colour=discord.Colour.red(),
            description="An error occurred while searching for your blacklist entry. Please try again."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if not existing_record:
        embed = discord.Embed(
            title="❌ Not Found",
            colour=discord.Colour.orange(),
            description="You are not currently in the blacklist, so there's nothing to appeal."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    
    if existing_record.get('list_type') != 'blacklist':
        embed = discord.Embed(
            title="❌ Not Blacklisted",
            colour=discord.Colour.orange(),
            description="You are only in the greylist. Appeals are only for blacklist entries."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if existing_record.get('nation_id'):
        target_nation_id = existing_record.get('nation_id')

    proposal_data = {
        'reason': f"Appeal by {interaction.user}: {reason}",
        'original_entry': existing_record,
        'excluded_voter': str(interaction.user.id)
    }

    try:
        ticket_channel, poll_message = await voting_manager.create_voting_ticket(
            interaction.guild,
            "remove",
            target_name,
            target_discord_id,
            target_nation_id,
            json.dumps(proposal_data),
            interaction.user
        )

        if ticket_channel and poll_message:
            embed = discord.Embed(
                title="✅ Appeal Submitted",
                colour=discord.Colour.blue(),
                description=f"Your appeal has been submitted for voting.\n\n"
                           f"**Channel:** {ticket_channel.mention}\n"
                           f"**Duration:** {POLL_DURATION_HOURS} hours\n"
                           f"**Required:** 2/3 majority to approve your appeal\n"
                           f"**Note:** Your own vote will not count towards the final result."
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                colour=discord.Colour.red(),
                description="Failed to create appeal voting ticket. Please check with administrators."
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        embed = discord.Embed(
            title="❌ Error",
            colour=discord.Colour.red(),
            description=f"Failed to create appeal voting ticket: {str(e)}"
        )

    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="add_evidence", description="Submit additional evidence with voting for acceptance")
async def add_evidence(
    interaction: discord.Interaction,
    evidence: discord.Attachment,
    description: str = None
):
    await interaction.response.defer(ephemeral=True)
    

    result = supabase.table("voting_tickets").select("*").eq("ticket_channel_id", str(interaction.channel.id)).eq("status", "active").execute()
    
    if not result.data:
        embed = discord.Embed(
            title="❌ Not a Voting Ticket",
            colour=discord.Colour.red(),
            description="This command can only be used in active voting ticket channels."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    embed = discord.Embed(
        title="📎 Evidence Submission",
        colour=discord.Colour.blue(),
        description=f"**Submitted by:** {interaction.user.mention}\n"
                   f"**Description:** {description or 'No description provided'}\n"
                   f"**Evidence:** [View Evidence]({evidence.url})",
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="Voting Instructions",
        value=f"Vote below to accept or reject this evidence. Voting period: {EVIDENCE_VOTE_DURATION_MINUTES} minutes.",
        inline=False
    )
    

    duration = max(1, min(24, math.ceil(EVIDENCE_VOTE_DURATION_MINUTES / 60)))
    poll = discord.Poll(
        question="Should this evidence be accepted for the case?",
        duration=timedelta(hours=duration),
        multiple=False
    )
    
    poll.add_answer(text="Accept Evidence", emoji="✅")
    poll.add_answer(text="Reject Evidence", emoji="❌")
    

    evidence_message = await interaction.channel.send(embed=embed, poll=poll)
    

    expires_at = datetime.utcnow() + timedelta(minutes=EVIDENCE_VOTE_DURATION_MINUTES)
    
    evidence_data = {
        "message_id": str(evidence_message.id),
        "ticket_channel_id": str(interaction.channel.id),
        "evidence_url": evidence.url,
        "evidence_description": description,
        "submitted_by": str(interaction.user.id),
        "expires_at": expires_at.isoformat()
    }
    
    supabase.table("evidence_votes").insert(evidence_data).execute()
    

    confirm_embed = discord.Embed(
        title="✅ Evidence Submitted",
        colour=discord.Colour.green(),
        description=f"Your evidence has been submitted for voting. The poll will automatically close in {EVIDENCE_VOTE_DURATION_MINUTES} minutes."
    )
    await interaction.followup.send(embed=confirm_embed, ephemeral=True)

@bot.tree.command(name="edit_entry", description="Edit existing blacklist or greylist entries")
@app_commands.describe(
    names="The members whose entries to edit (separate multiple with spaces or use mentions)",
    edit_mode="Whether to replace the current values or add to them",
    list_type="Which list to edit (blacklist, greylist, or both)"
)
@app_commands.choices(edit_mode=[
    app_commands.Choice(name="Replace - Completely replace the current values", value="replace"),
    app_commands.Choice(name="Append - Add to the current values", value="append")
])
@app_commands.choices(list_type=[
    app_commands.Choice(name="Both lists", value="both"),
    app_commands.Choice(name="Blacklist only", value="blacklist"),
    app_commands.Choice(name="Greylist only", value="greylist")
])
async def edit_entry(
    interaction: discord.Interaction,
    names: str,
    edit_mode: str,
    list_type: str = "both",
    nation_id: str = None,
    proof: discord.Attachment = None,
    reason: str = None,
    proof2: discord.Attachment = None,
    proof3: discord.Attachment = None,
    pos_alts: str = None
):
    await interaction.response.defer(ephemeral=True)
    if not (any(role.id == COMMISSIONER_ID for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)
    

    import re
    

    user_ids = []
    

    mentions = re.findall(r'<@!?(\d+)>', names)
    user_ids.extend(mentions)
    

    raw_ids = re.findall(r'\b(\d{17,19})\b', names)
    user_ids.extend(raw_ids)
    

    user_ids = list(dict.fromkeys(user_ids))
    
    if not user_ids:
        embed = discord.Embed(
            title="❌ Invalid Input",
            colour=discord.Colour.red(),
            description="Please provide valid Discord users. You can use mentions (@user) or user IDs.\n\nExample: `@user1 @user2` or `123456789 987654321`"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    fields_to_update = {}
    
    if nation_id is not None:
        fields_to_update['nation_id'] = nation_id
        fields_to_update['nation_url'] = f"https://www.politicsandwar.com/nation/id={nation_id}"
    
    if reason is not None:
        fields_to_update['reason'] = reason
    
    if pos_alts is not None:
        fields_to_update['possible_alts'] = pos_alts
    

    proof_urls = []
    if proof:
        proof_urls.append(proof.url)
    if proof2:
        proof_urls.append(proof2.url)
    if proof3:
        proof_urls.append(proof3.url)
    
    if proof_urls:
        fields_to_update['proof_urls'] = ', '.join(proof_urls)
    
    if not fields_to_update:
        embed = discord.Embed(
            title="❌ No Fields to Update",
            colour=discord.Colour.red(),
            description="Please provide at least one field to update (nation_id, reason, proof, proof2, proof3, or pos_alts)."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    existing_entries = []
    not_found_ids = []
    
    for user_id in user_ids:
        record = await blacklist_manager.search_person(user_id)
        if record:
            existing_entries.append(user_id)
        else:
            not_found_ids.append(user_id)
    
    if not existing_entries:
        embed = discord.Embed(
            title="❌ No Entries Found",
            colour=discord.Colour.orange(),
            description="None of the specified users were found in the blacklist or greylist."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    all_results = []
    
    for field, value in fields_to_update.items():
        results = await blacklist_manager.edit_multiple_people(existing_entries, field, value, str(interaction.user), edit_mode, list_type)
        all_results.extend(results)
    

    successful_user_ids = set()
    failed_user_ids = set()
    
    for user_id, result in all_results:
        if result and result != False:
            successful_user_ids.add(user_id)
        else:
            failed_user_ids.add(user_id)
    

    failed_user_ids = failed_user_ids - successful_user_ids
    

    desc_parts = []
    
    if successful_user_ids:
        desc_parts.append(f"**✅ Successfully Updated ({len(successful_user_ids)}):**")
        for user_id in list(successful_user_ids)[:10]:
            try:
                user = await bot.fetch_user(int(user_id))
                desc_parts.append(f"• {user.mention}")
            except:
                desc_parts.append(f"• <@{user_id}>")
        
        if len(successful_user_ids) > 10:
            desc_parts.append(f"• ... and {len(successful_user_ids) - 10} more")
    
    if failed_user_ids:
        desc_parts.append(f"\n**❌ Failed to Update ({len(failed_user_ids)}):**")
        for user_id in list(failed_user_ids)[:5]:
            try:
                user = await bot.fetch_user(int(user_id))
                desc_parts.append(f"• {user.mention}")
            except:
                desc_parts.append(f"• <@{user_id}>")
    
    if not_found_ids:
        desc_parts.append(f"\n**⚠️ Not Found in Lists ({len(not_found_ids)}):**")
        for user_id in not_found_ids[:5]:
            try:
                user = await bot.fetch_user(int(user_id))
                desc_parts.append(f"• {user.mention}")
            except:
                desc_parts.append(f"• <@{user_id}>")
    

    updated_fields = []
    if nation_id:
        updated_fields.append(f"Nation ID: {nation_id}")
    if reason:
        updated_fields.append(f"Reason: {reason}")
    if pos_alts:
        updated_fields.append(f"Possible Alts: {pos_alts}")
    if proof_urls:
        updated_fields.append(f"Proof URLs: {len(proof_urls)} file(s)")
    
    mode_display = "Replaced" if edit_mode == "replace" else "Added to"
    
    desc_parts.extend([
        f"\n**Fields Updated:** {', '.join(updated_fields)}",
        f"**Action:** {mode_display}",
        f"**List Type:** {list_type.title()}",
        f"**Modified By:** {interaction.user.mention}",
        f"**Modified Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])
    

    if failed_user_ids and not successful_user_ids:
        color = discord.Colour.red()
        title = "❌ Update Failed"
    elif failed_user_ids:
        color = discord.Colour.orange()
        title = "⚠️ Partial Update Complete"
    else:
        color = discord.Colour.green()
        title = "✅ Entries Updated"
    
    embed = discord.Embed(
        title=title,
        colour=color,
        description='\n'.join(desc_parts)
    )
    

    if proof_urls:
        proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls)])
        embed.add_field(name="Proof Added/Updated", value=proof_text, inline=False)
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="edit_company_entry", description="Edit existing company blacklist or greylist entries")
@app_commands.describe(
    company_names="Company names to edit (separate multiple with commas)",
    edit_mode="Whether to replace the current values or add to them",
    list_type="Which list to edit (blacklist, greylist, or both)"
)
@app_commands.choices(edit_mode=[
    app_commands.Choice(name="Replace - Completely replace the current values", value="replace"),
    app_commands.Choice(name="Append - Add to the current values", value="append")
])
@app_commands.choices(list_type=[
    app_commands.Choice(name="Both lists", value="both"),
    app_commands.Choice(name="Blacklist only", value="blacklist"),
    app_commands.Choice(name="Greylist only", value="greylist")
])
async def edit_company_entry(
    interaction: discord.Interaction,
    company_names: str,
    edit_mode: str,
    list_type: str = "both",
    owner: str = None,
    personnel: str = None,
    alts: str = None,
    reason: str = None,
    proof: discord.Attachment = None,
    proof2: discord.Attachment = None,
    proof3: discord.Attachment = None
):
    await interaction.response.defer(ephemeral=True)
    

    company_list = [name.strip() for name in company_names.split(',') if name.strip()]
    
    if not company_list:
        embed = discord.Embed(
            title="❌ Invalid Input",
            colour=discord.Colour.red(),
            description="Please provide valid company names separated by commas."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    fields_to_update = {}
    
    if owner is not None:
        fields_to_update['owner'] = owner
    
    if personnel is not None:
        fields_to_update['personnel'] = personnel
    
    if alts is not None:
        fields_to_update['alts'] = alts
    
    if reason is not None:
        fields_to_update['reason'] = reason
    

    proof_urls = []
    if proof:
        proof_urls.append(proof.url)
    if proof2:
        proof_urls.append(proof2.url)
    if proof3:
        proof_urls.append(proof3.url)
    
    if proof_urls:
        fields_to_update['proof_urls'] = ', '.join(proof_urls)
    
    if not fields_to_update:
        embed = discord.Embed(
            title="❌ No Fields to Update",
            colour=discord.Colour.red(),
            description="Please provide at least one field to update."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    existing_companies = []
    not_found_companies = []
    
    for company_name in company_list:
        record = await blacklist_manager.search_company(company_name)
        if record:
            existing_companies.append(company_name)
        else:
            not_found_companies.append(company_name)
    
    if not existing_companies:
        embed = discord.Embed(
            title="❌ No Companies Found",
            colour=discord.Colour.orange(),
            description="None of the specified companies were found in the blacklist or greylist."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    

    all_results = []
    
    for company_name in existing_companies:
        for field, value in fields_to_update.items():
            result = await blacklist_manager.edit_company(company_name, field, value, str(interaction.user), edit_mode, list_type)
            all_results.append((company_name, result))
    

    successful_companies = set()
    failed_companies = set()
    
    for company_name, result in all_results:
        if result and result != False:
            successful_companies.add(company_name)
        else:
            failed_companies.add(company_name)
    
    failed_companies = failed_companies - successful_companies
    

    desc_parts = []
    
    if successful_companies:
        desc_parts.append(f"**✅ Successfully Updated ({len(successful_companies)}):**")
        for company in list(successful_companies)[:10]:
            desc_parts.append(f"• {company}")
        
        if len(successful_companies) > 10:
            desc_parts.append(f"• ... and {len(successful_companies) - 10} more")
    
    if failed_companies:
        desc_parts.append(f"\n**❌ Failed to Update ({len(failed_companies)}):**")
        for company in list(failed_companies)[:5]:
            desc_parts.append(f"• {company}")
    
    if not_found_companies:
        desc_parts.append(f"\n**⚠️ Not Found in Lists ({len(not_found_companies)}):**")
        for company in not_found_companies[:5]:
            desc_parts.append(f"• {company}")
    

    updated_fields = []
    for field, value in fields_to_update.items():
        if field == 'proof_urls':
            updated_fields.append(f"Proof URLs: {len(proof_urls)} file(s)")
        else:
            updated_fields.append(f"{field.title()}: {value}")
    
    mode_display = "Replaced" if edit_mode == "replace" else "Added to"
    
    desc_parts.extend([
        f"\n**Fields Updated:** {', '.join(updated_fields)}",
        f"**Action:** {mode_display}",
        f"**List Type:** {list_type.title()}",
        f"**Modified By:** {interaction.user.mention}",
        f"**Modified Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])
    

    if failed_companies and not successful_companies:
        color = discord.Colour.red()
        title = "❌ Update Failed"
    elif failed_companies:
        color = discord.Colour.orange()
        title = "⚠️ Partial Update Complete"
    else:
        color = discord.Colour.green()
        title = "✅ Company Entries Updated"
    
    embed = discord.Embed(
        title=title,
        colour=color,
        description='\n'.join(desc_parts)
    )
    
    if proof_urls:
        proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls)])
        embed.add_field(name="Proof Added/Updated", value=proof_text, inline=False)
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="search_company", description="Search the company blacklist and greylist by name")
async def search_company(interaction: discord.Interaction, company_name: str):
    await interaction.response.defer()
    if not (any(role.name == OBRC_MEMBER_NAME for role in interaction.user.roles)):
        return await interaction.followup.send("You don't have the required permission level", ephemeral=True)
    
    record = await blacklist_manager.search_company(company_name)
    
    if record:
        list_type = record.get('list_type', 'blacklist')
        
        if list_type == 'blacklist':
            title = "🚨 Company Blacklist Entry Found"
            color = discord.Colour.red()
        else:
            title = "⚠️ Company Greylist Entry Found"
            color = discord.Colour.orange()
        
        embed = discord.Embed(
            title=title,
            colour=color
        )
        embed.add_field(name="Company", value=record["company_name"], inline=False)
        embed.add_field(name="List", value=list_type.title(), inline=True)
        embed.add_field(name="Owner", value=record.get("owner", "N/A"), inline=True)
        embed.add_field(name="Personnel", value=record.get("personnel", "None"), inline=True)
        embed.add_field(name="Alts", value=record.get("alts", "None"), inline=True)
        embed.add_field(name="Reason", value=record["reason"], inline=False)
        
        if record.get("proof_urls"):
            proof_urls = record["proof_urls"].split(', ')
            proof_text = '\n'.join([f"[Proof {i+1}]({url})" for i, url in enumerate(proof_urls) if url])
            embed.add_field(name="Proof", value=proof_text, inline=False)
        
        embed.add_field(name="Added By", value=record.get("added_by", "N/A"), inline=True)
        embed.add_field(name="Date Added", value=record.get("date_added", "N/A"), inline=True)
        
        if record.get('last_modified'):
            embed.add_field(name="Last Modified", value=f"{record.get('last_modified', 'N/A')} by {record.get('modified_by', 'N/A')}", inline=False)
    else:
        embed = discord.Embed(
            title="✅ All Clear",
            colour=discord.Colour.green(),
            description=f"No entry found for company **{company_name}**."
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="export", description="Export blacklist or greylist data")
@app_commands.describe(
    format_type="Export format",
    list_type="Which list to export"
)
@app_commands.choices(format_type=[
    app_commands.Choice(name="Excel (.xlsx)", value="excel"),
    app_commands.Choice(name="Google Sheets", value="google_sheets")
])
@app_commands.choices(list_type=[
    app_commands.Choice(name="Blacklist (People)", value="blacklist"),
    app_commands.Choice(name="Greylist (People)", value="greylist"),
    app_commands.Choice(name="Company Blacklist", value="blacklist_coo"),
    app_commands.Choice(name="Company Greylist", value="greylist_coo")
])
async def export_blacklist(interaction: discord.Interaction, format_type: str, list_type: str = "blacklist"):
    await interaction.response.defer(ephemeral=True)

    if not any(role.name in OBRC_MEMBER_NAME for role in interaction.user.roles):
        await interaction.followup.send("You don’t have permission to use this.", ephemeral=True)
        return
    
    try:
        records = await blacklist_manager.get_all_records(list_type)
        
        if not records:
            embed = discord.Embed(
                title="❌ No Data",
                colour=discord.Colour.orange(),
                description=f"No records found in the {list_type} to export."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        df = pd.DataFrame(records)
        if 'id' in df.columns:
            df = df.drop('id', axis=1)
        
        if format_type == "excel":
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=list_type.title())
            
            buffer.seek(0)
            file = discord.File(buffer, filename=f"{list_type}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            
            embed = discord.Embed(
                title="✅ Export Complete",
                colour=discord.Colour.green(),
                description=f"Exported {len(records)} records from {list_type} to Excel file."
            )
            
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            
        elif format_type == "google_sheets":
            try:
                client = get_client()
                
                sheet_name = f"{list_type.title()} Export {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                spreadsheet = client.create(sheet_name)
                worksheet = spreadsheet.sheet1
                
                headers = list(df.columns)
                worksheet.insert_row(headers, 1)
                

                for i, row in df.iterrows():
                    worksheet.insert_row(list(row), i + 2)
                

                spreadsheet.share('', perm_type='anyone', role='reader')
                
                embed = discord.Embed(
                    title="✅ Export Complete",
                    colour=discord.Colour.green(),
                    description=f"Exported {len(records)} records from {list_type} to Google Sheets.\n[Click here to view]({spreadsheet.url})"
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Export Failed",
                    colour=discord.Colour.red(),
                    description=f"Failed to export to Google Sheets: {str(e)}"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    except Exception as e:
        embed = discord.Embed(
            title="❌ Export Failed",
            colour=discord.Colour.red(),
            description=f"Failed to export data: {str(e)}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.event
async def on_member_join(member):
    try:
        await auto_role_manager.check_and_assign_roles(member)
    except Exception as e:
        print(f"Error in on_member_join auto-role: {e}")

@bot.event
async def on_poll_vote_add(poll_vote):
    try:
        poll = poll_vote.poll


        result = supabase.table("voting_tickets").select("*").eq("poll_message_id", str(poll.message_id)).execute()
        
        if not result.data:
            return

        guild = bot.get_guild(1319746765771116615)
        user = guild.get_member(poll_vote.user_id) if guild else None

        answer_text = poll.answers[poll_vote.answer_id].text if 0 <= poll_vote.answer_id < len(poll.answers) else "Unknown"

        print(f"✅ {user} voted '{answer_text}' in managed poll '{poll.question}'")

    except Exception as e:
        print(f"Error in on_poll_vote_add: {e}")

@bot.event
async def on_poll_vote_remove(poll_vote):
    try:
        poll = poll_vote.poll

        result = supabase.table("voting_tickets").select("*").eq("poll_message_id", str(poll.message_id)).execute()
        
        if not result.data:
            return

        guild = bot.get_guild(1319746765771116615)
        user = guild.get_member(poll_vote.user_id) if guild else None

        answer_text = poll.answers[poll_vote.answer_id].text if 0 <= poll_vote.answer_id < len(poll.answers) else "Unknown"

        print(f"❌ {user} removed vote '{answer_text}' in managed poll '{poll.question}'")

    except Exception as e:
        print(f"Error in on_poll_vote_remove: {e}")

@bot.event
async def on_ready():
    print(f'🤖 {bot.user} is ready!')
    print(f'📊 Supabase connected successfully')
    try:
        synced = await bot.tree.sync()
        print(f'⚡ Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')
    

    bot.loop.create_task(poll_checker_task())

async def poll_checker_task():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            await voting_manager.check_expired_polls(bot)
        except Exception as e:
            print(f"Error in poll checker task: {e}")
        

        await asyncio.sleep(300)

bot.run(os.getenv("BOT_KEY"))