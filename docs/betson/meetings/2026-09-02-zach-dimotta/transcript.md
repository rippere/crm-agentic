# Call with Zachary DiMotta — Transcript

**Recorded:** 2026-09-02, 9:07 PM · **Duration:** 1h 07m · **Source:** `Call with Zachary DiMotta-20260902_140735-Meeting Recording` (Betson Teams)
**Participants:** Benjamin Rippere (Ben) · Zachary DiMotta (Zach)

> Auto-transcribed (Teams). Numeric speaker-id artifacts stripped; speaker + `M:SS` timestamps preserved for citation. Redactions `****` are from the source.

---

Call with Zachary DiMotta-20260902_140735-Meeting Recording

September 2, 2026, 9:07PM

**Ben** · `0:06`
Okay, um...So...I am trying to implement this whole lead generation and warm leads function within the CRM. And it's not currently in production, but I can show you kind of what it is. I built this in like...

**Zach** · `0:28`
When you say CRM, is it, are you talking about Salesforce or is it something different?

**Ben** · `0:34`
This is something different. I built it initially as a like a layover for Salesforce. So initially, how I got this internship was I showed Mike this product that I built and he was like, yeah, this is this is cool. This is way less clunky than Salesforce.

**Zach** · `0:35`
Okay.

**Ben** · `0:53`
I don't know if you're familiar with Betson Salesforce configuration, right?

**Zach** · `0:58`
Yeah, not that familiar with it. We kind of adopted it like right before or not too long before I left. And we went through, I mean, I remember, I think it was like, is it Bri Dukes maybe is her name? Yeah, we kind of went through it and unfortunately the

**Ben** · `1:15`
Mhm.

**Zach** · `1:19`
The fact of the matter was is that they had built something.really kind of like specified or spec'd out for bets and salespeople. And yeah, and...

**Ben** · `1:28`
And then.Send emails, yeah.

**Zach** · `1:34`
the imperial, the billiard business, was just very different. So I would look at it and be like, all right, well, this like, this works. And then like, and then a bunch of it, like all the really cool functionality, like just didn't really work for us. I don't know, maybe it worked for Betson, but like, I, we weren't Betson. Like we didn't have equipment and.

**Ben** · `1:49`
Mhm.

**Zach** · `1:56`
like all these things and there just wasn't really an appetite, let's say, to modify it, you know, that it did, because I don't want to like waste time, you know, like I grew up, I did 20 years of Imperial sales without Salesforce. Do I see the value of a good CRM?100% I see the value of a good CRM. Do I see the value in a...****** CRM? Like, no, of course not. So it's kind of where we're at.

**Ben** · `2:25`
Yeah.Yeah, I know that Bill, Bill Seibert is working out a full redesign, but I just, I've been kept away from that because it's more.He likes his echo chamber is what it seems. So Mike wants to see if this piece or this thing that I built is viable for some aspect because integrating any sort of agentic operational layer into Salesforce is just like...the headache, especially with how they're already redesigning it. So.

**Zach** · `3:02`
Yeah.

**Ben** · `3:06`
Yeah, I would love to get some of your feedback on this specifically.

**Zach** · `3:10`
Yeah, I mean, like I think I told you the other day, you know, we at my last job we started, we brought in HubSpot and it kind of lived alongside of Salesforce, not Salesforce, sorry, Shopify.

**Ben** · `3:19`
Mhm.

**Zach** · `3:25`
And...you know, I'm sure you're aware, but like any of these larger software companies, when you're in that honeymoon phase or that courting phase, like, oh yeah, no, it'll work, it'll work, it'll work, it'll integrate, it'll integrate, and then it doesn't really integrate unless you go and you, you know, get a developer to do a lot of these things. SoSo HubSpot did integrate a little bit with Shopify, not to the degree that we were hoping. And then, you know, ultimately, because we were such a small company and looking for, you know, wanting to keep the, you know, we were, I think the owner and I were okay with spending money on the technology as long as it worked, because there really,The golden, you know, the what we were really looking for was.Phone, e-mail.order, entry, inventory, all integrating with the CRM. And then it was just like, sky's the limit. And it got close. Like if you use the HubSpot phone system, like it was pretty slick. And then even with, we used RingCentral as our voice, our VoIP system.And it's still integrated. Like I was able to do it. Like I was able to do some of the plugins along with this other kid that was working there.

**Ben** · `4:50`
Your voice system as in like call transcription or you telling the CRM what you want to learn about the data?

**Zach** · `4:54`
Just, no, no, it was, it was so you, so you could do a bunch of stuff, yeah, so Ring Central.was just our telephone system, right? And you could have a physical phone if you wanted, or most people just use the Ring app on their cell phones. And so it would actually capture the inbound phone call or outbound call.

**Ben** · `5:17`
Mhm.

**Zach** · `5:21`
you know, using caller ID would say, okay, you know, this was obviously a, you know, we would, it was like hardware stores that would call in a lot of times. So like Ben, you know, or you know, Ben's hardware store called. And if you wanted to, you could absolutely.Turns, flip some switches, and then...get an actual transcription of the phone call or the e-mail. So like, hey, I'm having a problem with this, or hey, I'd like to order that, or hey, can you tell me a little bit about this? And then ultimately HubSpot would take all of that, and it would, you know, we could set up rules to say, okay.Ben's Hardware Store, great store, six store chain in the Midwest, or you know, in Washington.

**Ben** · `6:09`
And it would populate the data of it.

**Zach** · `6:11`
It would just populate that data, but also too, what was really, really cool about it was it would set reminders for the salesperson. So like, and then also too, if Ben's Hardware placed an order on our website, it would also register. So really at the end of the day, like as a sales manager, I was, I wanted my salespeople to make sure they were.

**Ben** · `6:12`
Sure.Mhm.

**Zach** · `6:31`
They were actively, proactively talking to Ben's hardware once every 30 days, once every 60 days, and you know, so it was it was pretty interesting, and it would, you know, give people reminders like you'd come in the morning and be like, "Okay, hey, today is the day you gotta call Ben's hardware because you haven't spoken to them in 60 days," like that's...

**Ben** · `6:37`
Yeah.Yeah.Mhm.

**Zach** · `6:53`
From a sales managerial perspective, even from a salesperson perspective, that's like the holy grail.

**Ben** · `6:59`
Yeah.

**Zach** · `6:59`
You know, like just getting a reminder like A accounts, B accounts, C accounts. Like what are the requirements as a salesperson, you know, that as a sales manager that I want to set. Like C accounts, I want you to talk to them once every six months. B accounts, every three months.And if you don't hear from an A account once every 15 days, something's ******* wrong. So, you know, like, and just having that functionality was eventually, and we had started building it by.

**Ben** · `7:18`
Yeah.Mhm.

**Zach** · `7:34`
It was getting there, and for a couple of $1,000,000 company, it was a really big deal. You know, you could really manage a large account base of, you know, 6 or 700 accounts with like 2 people. Like, that's a really big deal.you know, active accounts. That's, I think that's a really big deal because I think.

**Ben** · `7:53`
Yeah, like having like the face to the name and being able to refresh the deal history between the person while having it in the loop is like vital to the sales, you'd say. Yeah.

**Zach** · `8:05`
Totally.Totally, yeah, and I mean, I think just with like a with a with a CRM like HubSpot, what was what was cool is that you know you could set up these reminders or these flags and and you know the first few things like with the automated like e-mail sequences and this and that, like.If we haven't heard from, you know, for all those C accounts, if we haven't heard from those accounts in, let's say, the rule is 6 months, but let's say after four months of not hearing from those C accounts, we could have an automated e-mail sent out and it would just say like, hey Ben, it's Zach from Vermont Natural Coatings.Been a little while, just want to check in, see how you're doing. And like you can even, it was really cool, like you could have these.I don't know what you call them, but just these sections of the e-mail that you could leave blank but put a code in and like it could reference the last order. Like, hey, like, hey, how'd that work out for you? Give me a holler if you want anything. Otherwise, I'll follow up in a few weeks. Like just stuff like that.

**Ben** · `9:05`
Yeah.And it pulls from the data set, yeah.

**Zach** · `9:15`
Yeah, just simple, easy touch points that I believe, you know.a salesperson with active accounts that's like relationship oriented.I honestly don't see how a single person...the old school way, like just, you know, pen and paper and Outlook and phones and how you, how you really, truly manage and grow more than say.

**Ben** · `9:37`
Yeah.

**Zach** · `9:44`
One 100 to 150 accounts.

**Ben** · `9:46`
Mhm.

**Zach** · `9:47`
Like if you really wanna grow. So anyway, that's where all this automation is really cool. And you know, whether it's AI or automation or whatever it is, like, you know, we can, we can discuss. But anyway, sorry, I'm just a bit of a download.

**Ben** · `9:56`
Yeah.I mean, that's great. I mean, you're painting a picture of what you want it to look like. And I mean, like, I'd say, here, I'm going to start sharing the software, or I'll try to, if this will open.Um...Yeah, I think it's great that you have an idea of what it should look like and I think it's going to be easier to form fit it to the exact needs that you'd like for it to be. Here's the pipeline or essentially like what I've built here. It looks pretty vibe coded.But I would say that it does a good job. This isn't pre-seeded or pre-populated, so I have a bunch of stuff that I do for my own work. Like all of this on this page is about my coding and each of my developments, all my projects that I work on.

**Zach** · `10:52`
Okay.

**Ben** · `10:55`
This isn't typically offered, but you have pretty much everything that you've been asking for. There's call transcription, there's auto-developing tasks.And it's definitely not going to look this way, just because I have a bunch of systems that fill into this and I use it as an observability layer.But I have my e-mail connected, or I did, I guess. And through the dashboard, like, I did a similar thing with the game room twin for Betson, where it has the technician walkthrough, and it's really simple. It's for a dude who didn't graduate high school. It's like...Yeah, here are my tasks. This is what I'm going to do. So it kind of lowers the cognitive bandwidth and the operational load. So you just know what needs to be done. So for example, I have an AI model running on like what you give to this. And I don't have any deals in here currently because I don't.

**Zach** · `11:47`
Yeah.

**Ben** · `11:56`
I'm not like working external to Betson other than like AI consulting. So if you would have deals in here, they'd go into the digest, they'd go into the contact health, and these would be graded on, you know, amount of outreach that you have, deal health alerts, and then that kind of feeds into all of these.

**Zach** · `12:01`
Yeah.

**Ben** · `12:16`
with the active agents and the agent activity. And then the contacts are akin to the pipeline. So the pipeline has the deals you have and then attributes the objects or the people that you are in contact with, which you can auto enrich with LinkedIn profile.their phone number that you find on the internet, their e-mail.Currently, it doesn't have any texting or calling featured, like that you can call them through this, or it just has the log a call, so you can connect your phone through a couple different external dependencies.

**Zach** · `12:49`
Sure.Yeah, I know, um, Air Call, like, I don't know, you know, I mean, obviously it's like the newest and latest and greatest. Air Call was the name of the app, the VoIP system that, that.Shopify was really pushing. But again, to your, I mean, to this, like, you know, for what we're going to use it for, for.photo booths, like that's probably not, you know, as long as there's like, hey, I made a call and I want to log it. Like I spoke with, you know, I spoke with Ben today. We talked about X, Y, or Z. And, you know, before I can close out that call log, you know, having like.

**Ben** · `13:23`
Mhm.

**Zach** · `13:35`
the next step, whether it's a drop down like, yeah, just like, hey, follow up in a month, follow up in six months, or just like flat out say it's like dead lead. Like it's just, this isn't going to go anywhere, drop it from the mix. You know, and I think, you know, I was talking with Mike about this too, and

**Ben** · `13:37`
The ticketing feature, sure.Yeah.

**Zach** · `13:55`
You know, I think like...I've never used a CRM like this because we never really, you know.like a pipeline. Like I understand pipelines are important for Betson because that's just kind of the way they work. With Imperial Retail, there was no pipeline, right? Like you talk to the guy for the first time and then he could buy something, right? And that was the pipeline. And it was more about following up and saying hi and making sure, you know,

**Ben** · `14:13`
So, all handshakes.

**Zach** · `14:23`
from a Betson perspective, from like a, even if like I lead with photo booths.Let's just keep it simple. I don't want to get ahead of myself, but like, this is awesome, right? And a year or two from now.this system or we start to understand or the system starts to understand like, what are the attributes of a location that make it successful? And I think that's where, you know, I think we talked about it where it's like,

**Ben** · `14:50`
Yeah.Mhm.

**Zach** · `14:56`
that initial setup form. Like, tell me about your location. Like, let's look at the surrounding area. And when there's AI involved, and it can say like, oh, this is, you know, it's this amount of distance from an airport, it's this amount of distance from a school, it's this amount of distance from, you know, whatever it might be. And then this is the size of the venue. This is what the venue does.

**Ben** · `14:59`
Yeah.

**Zach** · `15:18`
Like, and then from a lead generation standpoint, it's like, all right.You know, why can't, you know, can the machine, can the AI just say like, all right, Zach, based on this information, you're going after the state of Texas. In Dallas,These are, you know, again, it's obviously it's not talking to me, but like, these are the most successful photo booths in Dallas. Based on this, go find all of those same venues in Houston and in San Antonio and, you know, Fort Worth. And like, that's your lead generation. Like, we want quality over quantity.

**Ben** · `15:42`
It'll lay it out for you.What it sounds like to me that you're asking for is that you would like it to remain as simple as possible and streamlined. Am I getting that right?

**Zach** · `16:07`
Yeah, like, I mean, again, so...

**Ben** · `16:13`
Because I know that like starting out with something that might have all these bells and whistles is a little bit daunting, but in order to get the amount of KPIs and like the metrics that we need to create that profile of what the best photo booth is going to be down the line when we have tangible data coming in.All of these systems will aid in that. So like, for example, the call summarization, I might not have the texting and the calls hooked up to this currently, but there is a call summarization model. So you can press run right here and it'll start transcribing the call should it be on your system. So all I have to do is wire in some external dependency.

**Zach** · `16:36`
Yeah.

**Ben** · `16:52`
And then sentiment analyzer would be ingesting your emails and your calls or your messages with said company. Or it'll also ingest a like, yeah, had a call with this guy, went good, interested, call next week, planned. Like it takes all this.

**Zach** · `17:09`
Yeah, or yeah, or right.

**Ben** · `17:12`
And then as well, on top of that, it has the PM agent. So like that would be, you know, this location or this brand has six locations, blah, blah, blah. All of these people are reporting to this one guy, talk to them, and it just auto grades it. And then the e-mail composer is for the auto.the auto reach out or the auto outreach. Pipeline optimizer is for the priority of each deal. So like, should it be older? Should you reach out now? Should you reach out in five days? The semantics sorter is, it uses urgency and grading metrics.

**Zach** · `17:44`
Yeah.

**Ben** · `17:50`
on emails, so based on the intonation, stuff like that, it would change the priority in which deals are made. And then lead score does the same thing.

**Zach** · `17:58`
No, this is all awesome. It's all incredible. I guess so what you said before, like, so there's going to be the me kind of user, which whatever that means, right? I'm a 48 year old, you know, pool table salesman that, you know, loves this stuff and is into it.And then to your point earlier, you get the guy out of high school, or you just get somebody new, like the ramp time, like just because this is what my screen looks like with all the bells and whistles, and I kind of know how to use it, or maybe I'm really good at like, and I'm looking at each of these individual things. If I had like a junior person,that's new to the business and this and that, like, they might just not see all this, right? They might have their own view. And we do dumb it down, right? We simplify it for them. And we're just feeding them, right? Like we're feeding them leads. We're feeding them, call this guy today. And honestly, like, call this guy today, and this is what you're talking about.

**Ben** · `18:52`
Mhm.

**Zach** · `18:56`
Right, because we can get guys off the street that have a great gift of gab and don't mind and you know, you know, maybe aren't ************, but you know what I mean, like just the deck and riff. But all of this is super cool. And if there are ways to do this kind of stuff,

**Ben** · `19:06`
Mhm.

**Zach** · `19:15`
you know, in the background where it just does dump.a bunch of leads, but I think what you're saying is like, it can not only get leads, but it can act upon those leads potentially, like with e-mail templates that I develop or I help it, you know, I help it, you know, and it's still signed by me. I mean, ideally, at least at the beginning, like it could generate a bunch of emails.

**Ben** · `19:30`
Yeah.

**Zach** · `19:40`
and it just sits in like drafts and I go through the drafts and I just double check its work and then I'm just hitting send. But obviously I can do that a lot faster than pending, you know, 50 emails A day.

**Ben** · `19:47`
Mm-hmm.

**Zach** · `19:54`
Um...Right.

**Ben** · `20:09`
It has workers and it's routinely at night time. So any information that you attribute to an object, should it be a person or a project or a company, that will all get ingested and turned into the next day's report kind of thing. So all of these metrics are auto tracking, which is kind of what I thought you were asking for right there.

**Zach** · `20:30`
Yeah, yeah, and I think, I mean, I think ultimately...how we would probably like to operate certainly at the beginning.is that if we're just using like a fishing analogy, like this thing is choosing the rod, this thing's choosing the lure, this thing is choosing how far to cast it out, based on information it's pulling about the location, about the owner, about whatever it is. And then really honestly, like once they get hooked,once they hook that fish, that's when it's like, I'm okay being a human being taking over. Like, let me jump in. Like, and if it's telling me like, hey, you've got a meeting with like, on any of those automated emails that HubSpot would send out, there was a link, right? There was a link and it said, make an appointment.

**Ben** · `20:59`
Mhm.It will just put it on your calendar.

**Zach** · `21:20`
you know, make an appointment with me. And people actually did it. You know, like I was amazed, like, because I had never used it before. I had never used a system, you know, a program like that before. And, you know, whether people are just more accustomed to it, but also too, just like a flag saying, hey, this guy opened it.

**Ben** · `21:20`
Mhm.

**Zach** · `21:39`
Okay, cool. And then like, I know that there's a second e-mail going a week later because he opened it and he dwelled on it a little bit. You know, he had it open for 30 seconds and then he clicked a link and we don't want to be super creepy about it, but we do. And then, yeah, yeah, yeah. And then it was just like, all right, I'm not going to engage yet.

**Ben** · `21:45`
Yeah.But you can be, yeah.

**Zach** · `21:59`
And then because he clicked the link, the second trigger went out, and three days later, another follow-up e-mail. Hey, just checking in, see if he had a chance. If he opens that one, **** it, I'm calling.

**Ben** · `22:00`
Let it simmer.

**Zach** · `22:33`
Right.

**Ben** · `22:34`
It'll work with that. It just, it needs verifiable data and users on it. And I don't have any business where I could just put in 10,000 people and just call them up.

**Zach** · `22:47`
Yeah, I mean, that's the thing. Like, I have a call with Michael in marketing, I think, tomorrow or Friday. And yeah, like...what leads can you feed me? Like what are inbound leads that you can feed me? And then, you know,You know, I don't know if you've been to, you know, Betson.com slash revenue share. At the very bottom of that page is like a questionnaire. And it's kind of a ****** questionnaire, to be honest. Like it's not a very good questionnaire. And, you know, for in this particular case, like, you know, I think that's whereHow does this, what you're building or what you've built, interact with like a marketing?Program, you know, marketing system that were, you know.you know, what does that opening e-mail look like? You know, I know you popped it up on the screen, but like, and then what happens? Like what, what flyer do we, you know, where does it lead? Because right now, if you go to betson.com slash revenue share, like that's not a good page for this guy.

**Ben** · `23:39`
Yeah.

**Zach** · `23:55`
Like for non-traditional locations, like a bar or a nightclub or whatever, you know, a truck stop or, you know, whatever it might be, that page is not helpful because that page is talking directly to arcades.

**Ben** · `23:55`
Mm-hmm.

**Zach** · `24:12`
They're talking to people that either want to open an arcade.or already operate an arcade. We're going after people that have no idea, like we're presenting this idea. They've never, let's just, 90% of the people that we're gonna meet, 95% have never considered putting a photo booth in their location.

**Ben** · `24:32`
And the granularity of that, that that questionnaire is just awful for your use case, and make it makes sense.

**Zach** · `24:39`
Yeah, like, it's just like, we have to keep it simple. We have to make it inviting. We have to make it, you know, like, this isn't scary. This is, this is, and also too, like, we have, like I said, you know, at one point it was like,convincing people we're not actually selling anything.

**Ben** · `24:56`
Mhm.

**Zach** · `24:56`
Like, we're looking for partners.Like this is partner acquisition, not customer acquisition. You know, we're looking for people, what are traits? I mean, in this, you know, for the AI, like what are traits of the type of business that would lend itself to something like this? You know, which is interesting, right? Like.

**Ben** · `25:14`
Yeah.

**Zach** · `25:18`
So, anyway, um...Yeah, I mean, I think there's a...You know, I will say, like...You know I don't want to say I guess I don't want to say anything because I I've never used a CRM.With.so much like it is really interesting to think about a system that's looking, reviewing phone calls, looking at emails, looking at purchasing habits, looking at order history andIt using some kind of...You know, using some kind of logic to say this customer is going from hot to cold.

**Ben** · `26:07`
Mhm.

**Zach** · `26:07`
Like what is like, that's really interesting. Like what? I've never used it like that. That's always kind of been up here like, oh yeah, he doesn't call me as much. He doesn't call me as much as he used to. Oh, like, you know what? He's not, you know, he was ordering. I'm just going to say pool tables like or cue sticks. He was ordering ordering one piece cues.

**Ben** · `26:15`
Yeah.

**Zach** · `26:28`
like clockwork and then he stopped. And chances are when you have 100 plus customers, you can't identify that as a human being.

**Ben** · `26:35`
Okay.Yeah.

**Zach** · `26:39`
Right? Until you're actively looking at your sales by category, by then by SKU, and you're like, ****, why are my 12 111s, you know, my 12 dash 111s, which is our old one piece Q SKU? Why are those sales down? Oh, ****. Ben's not buying one piece. He hasn't bought one piece Qs for me in six months.When the hell did that happen? And then you call and it's too late.

**Ben** · `27:04`
Yeah.

**Zach** · `27:05`
Right? Some other guy got their hook. Again, that's not this, but like that's really interesting from a, you know, I do love like from an automated e-mail stem I was telling Mike, like I love, and granted I might be an idiot, but like I have the Amazon credit card and we buy everything from Amazon. I don't use this credit card for anything else except for Amazon.because I get 6% cash back on everything we buy from Amazon. And I love my quarter, I don't love, I don't like actively look for it, but when it shows up, a quarterly e-mail from Amazon telling me how much money I'm saving using their credit card.

**Ben** · `27:40`
Mhm.

**Zach** · `27:45`
and it has all of the data. It has how many orders, what the total dollar value was, how much I saved, and being a Prime member, and it's all ********. But I imagine that that kind of e-mail, that like, well, yeah, it's like, it makes me, it's like, you know what?

**Ben** · `28:00`
It makes you feel warm.That has that has all of it attributed to to your history.

**Zach** · `28:04`
That's, it's reminding me why. And I think that's what's, that could be interesting with the photo booth category is like quarterly emails to the owner, to the right person to say, you had 300 people take pictures, you had this and that, you had this many people tag your location.on socials, you made X, I mean, the dollars almost become, you know, for me from like a branding standpoint, like, yeah, you know what, you made $2,000 in Q1. That's awesome. Like you're trending up over last Q1. Like good information, like, you know, good information, and whether it's good or bad,

**Ben** · `28:37`
Yeah.Mhm.

**Zach** · `28:46`
right, like businesses up, businesses are down. If nothing else, it's like, hopefully the system has alerted me like, hey.

**Ben** · `28:53`
It gives you this sense of control, I think, is what, yeah.

**Zach** · `28:56`
It gives you a sense of control and it also, like, this is the right partner. This is who you want to use, right? And...

**Ben** · `29:00`
Mhm.This guy cares about my business and he wants this business to continue. This is fantastic. Like, I think when you mentioned this is not that before, when you were saying like, it doesn't have all the attribution of data within your pipeline, say you're using, like how Vetson does, say you're using Salesforce and then you're exporting some of the data to here.

**Zach** · `29:07`
Right.

**Ben** · `29:23`
it does, it can do that. So having like saying that it's not able to or like setting the sights a little short of what it could be, like I'm fully prepared to turn this into a vertical product instead of having a wide breadth. Like being able to form fit it to the industry allows for much more.Like a higher velocity for going going for the gold, really. I mean, I hate to use the analogy here, but it works.

**Zach** · `29:49`
Yeah, it's...You know, I think I think with my experience, and you can take this for what it's worth, but again, like, you know, my demographic, whatever it is, right, you're like running a company or you're running this or this little segment of a business or whatever it is, because I've now kind of done, you know, a division of this business, a standalone.business in my last job and like this little section of the company with this thing.One of the things, because we went through, we looked at HubSpot, we looked at Salesforce, we looked at...Something else, but...The entire that entire experience, even afterwards, like we chose HubSpot and HubSpot's like, you know, number one, number, you know, #2 after Salesforce, whatever it is, the integration.

**Ben** · `30:37`
Yeah.

**Zach** · `30:43`
Experience is terrible without a doubt, and then you have all, it's like you, you, I would like if, if I were building a new...you know, these CRM companies pitch you all of this functionality, and then you get it, and out-of-the-box, there's all of these features. And it's like, I would almost prefer the experience to be like,

**Ben** · `31:04`
Mm-hmm.

**Zach** · `31:10`
start, you know, stage one, like do this for three, do this for three months, integrate your customers, start tracking emails and this and that. And then after three months, like phase two, it's like, and maybe it's, you know, they had like, you know, they have HubSpot Academy and all these things. After three months, it's like.

**Ben** · `31:13`
Sure, build it as you go.Mhm.

**Zach** · `31:29`
Now, let's start looking at sales analysis.

**Ben** · `31:33`
Is it the desire for illusion of choice here or is it just because of like the onboarding process is so aversive because there's so many moving parts? Like what would, and it's the thing about like most CRMs that are frontier is that like Salesforce, HubSpot, they pride themselves on their integration. And if most users, and you're not the first person I've heard this from.they say that the experience is terrible or it's hard to configure. Like what about that would make it easier? Is it just like narrowing the funnel?

**Zach** · `32:03`
B.The only, yeah, I don't know, like, you know, honestly, like, for me.If I worked at HubSpot.Because again, like the sales guys are just, they're used car, they're used car salesmen, right? These things basically, not that it's the same thing, but it's, I actually had a handyman tell me this once. He's like, that has a tail light warranty. When you see the tail, when you see my tail lights pull out of your driveway, warranty's over. Like that's the feeling that you get.

**Ben** · `32:20`
Mmh.

**Zach** · `32:37`
And even after like, and you know, oh, we're always there for you and you can call 1-800 HubSpot and all that stuff like.There's no...One thing that would put any CRM company...truly above anybody else, and this might not be possible, is like, I love learning, I guess maybe for me, it's like, I love learning about people's businesses. I love learning how they operate, what they do, how they interact with their customers, how their salespeople work.

**Ben** · `33:04`
Mhm.

**Zach** · `33:09`
how their suppliers, you know, I enjoy, and I can learn it pretty quickly because at the end of the day, a widget is a widget. Like, I don't care what you're selling, it's a widget, right? Whether it's a service or a physical product or whatever it is. And then taking the time to just literally like, and maybe it's just talking to an AI.Right? Like, hey, it's Zachary. Yeah, I met with Ben's Hardware today and it's a very traditional hardware operation. They have six locations, they have 35 employees, you know, this, that, and the other thing. And it's just like,

**Ben** · `33:30`
Mhm.

**Zach** · `33:44`
There's nothing overly unique about what they do. So then it's just like, and it's like, all right, here's your hardware 101 CRM. Like, or like, hey, this is different. This is different. This is really what they're trying to accomplish. These are their goals.

**Ben** · `33:55`
Mhm.

**Zach** · `34:03`
And then...But ultimately it's the integration because if the data doesn't talk to the other one, it's challenging, but it's like, I don't like, I didn't like.You know, and it was same thing with Shopify. Granted, Shopify works ******* awesome.Shopify is great. I will say Shopify is not great for B2B.Shopify is great for B2C.or D to C, whatever you want to, whatever the, but B to B is terrible. It's not, it's not good and it could be better. I know there.

**Ben** · `34:41`
It's not geared in the sales department? Okay, sure.

**Zach** · `34:43`
Not yet, not yet, like that, yeah, just even even just how you set up a customer, like the the the framework of Shopify.

**Ben** · `34:49`
Yeah.

**Zach** · `34:53`
how you set up like you order from, you know, from Zach's whatever.com, like Ben orders one time or maybe orders again, like it works great.

**Ben** · `35:00`
The persona, the persona infill is clear, sure.

**Zach** · `35:03`
It works great for that. If you have, if you are a business with six locations, forget about it. It sucks. It sucks. But anyway.

**Ben** · `35:10`
Yeah.

**Zach** · `35:16`
No, it's again like.It would be what's interesting about...What's interesting about maybe this opportunity is that, you know, we could build something.Like having you here and listening and understanding, you know, I mean, I can only articulate so much. It's like, this is why this doesn't work. Or this is why this is, this is so close, man. If it could just do this, like it's just, it's awesome, right? Like it would just blow everybody's socks off.The fact that you're here and that we...

**Ben** · `35:50`
I mean, that's my entire job, like, here, here, that's that's yeah.

**Zach** · `35:52`
Right, like, well, that's what's cool.Yeah, that's what that's what's super cool about this opportunity, because like, I don't know what I don't know, right? But like, I do know how people buy. I do know how to like cast a cast a line out and hook somebody and bring reel them in. And then I do also understand, I understand the importance of

**Ben** · `35:55`
Um...No.Yeah.

**Zach** · `36:14`
you know, really identify, taking the time to identify the customer types and how each one of those customer types. And in this particular case, let's just say there's a half a dozen. There's not that many, right? There's just because they have six locations, there's still a bar or there's still a restaurant or there's still whatever, but it's like.

**Ben** · `36:19`
Mhm.Yeah.

**Zach** · `36:34`
Just some of the wordsmithing with the intro emails or the marketing materials can make all the difference in the world. And if it takes an extra few minutes or an extra few hours or an extra few days to kind of manipulate.those pieces of information. But you go from closing, yeah, you go from closing one out of 10 to three out of 10, it was worth the time.

**Ben** · `36:54`
It would make the B2B experience way more workable.Sure.That's why I'm trying to sponge as much up from really good salesmen like you and my, like it's just, I have the purview of the engineer, like it's not hard to me, but understanding how to close and how to get people to come back and build that relation and have that handshake every time is...is not transparent. Like, I'm not a used car salesman. That sounds like an awesome job, but being able to ingrain that into a product is exactly what we need.

**Zach** · `37:28`
Well, the thing is, is like...There's a, there's a great, there is a great.There is a need for used car salesmen in this world. I don't mean to disparage used car salesmen, you know, but that is like the tail light warranty. But in a lot of ways, what we're trying to do with photo booths is kind of like a used car salesman because it's not that it's the same thing, but like,the sales technique, just like wowing and this is amazing and you're never, you're not gonna regret this. This is gonna make you a bunch of money. It's gonna make me a bunch of money. This is, or, you know, but then having a CRM.

**Ben** · `37:58`
Mhm.

**Zach** · `38:10`
or an AI, whatever it might be like, imagine like there's this on the same day, on the same day, three months from now, you and I land a new photo booth customer, one in Florida, one in Texas, and they're just traveling along a similar path, right? And then...One day, maybe the guy from Florida calls me, is like, Zachary, you know, I remember you mentioned, or you know what, I got your e-mail. Three months later, I got your e-mail.Talk to me about cranes. Your e-mail talked to me about redemption cranes. I never really considered it. Is that something that, you know what, yeah, you should, let's give it a shot, man. Like here's, I'll send over a contract. Let's get a crane in there. The crane does more than the photo booth. It's awesome. He's near the rays.

**Ben** · `38:58`
Mm-hmm.

**Zach** · `39:01`
He's near the Rays Stadium and we put a bunch of Tampa Bay Rays stuff in the, and it goes, it blows the doors off.

**Ben** · `39:05`
Yeah.

**Zach** · `39:08`
The AI.in the system says, wait a second.

**Ben** · `39:12`
Sure, yeah.

**Zach** · `39:15`
This is doing really well over here. This guy didn't, this guy, this guy did get that e-mail, the guy in Texas, and he's right near the Rangers, Rangers ballpark.

**Ben** · `39:25`
Mhm.

**Zach** · `39:26`
Zach, make a phone call. Zach, pick up the phone. Like, that's where that gets super interesting, is where it's like, if it can start identifying success stories, and then, because that was always like my big thing with,

**Ben** · `39:32`
Yeah.

**Zach** · `39:41`
With the how I imagined.

**Ben** · `39:41`
trying to sell to somebody and telling them, hey, your neighbor, like I modeled the CRM that I built after all of the door-to-door salesman teams. Like they were the pioneers when it came to vibe coding and creating observability products for themselves where, you know, it's very reliable to go door-to-door and say, hey,You know, I'm serving Nancy right there, your neighbor, she loves the result. And like being able to draw that correlative design and also ingrain it with other products. Like right now, Betson probably is not desiring another CRM for them to configure, but down the road, should this work, being able to pull from Salesforce would and create these success stories for you to get on the phone and talk.

**Zach** · `40:07`
Totally.

**Ben** · `40:26`
Talk about is, it's it, it's very, very within scope.

**Zach** · `40:31`
Yeah, and I think just with like, you know, granted, this is this is work, this is a commercial application we're talking about, but real quick, like that was always seemed felt like the holy grail of this of a good CRM.slash maybe with some AI, like, you know, with Sidekick, with Shopify, you know, I just imagine that with Imperial, where, you know, Imperial, like the Shopify, like, you know, I might have to go prompt Sidekick, but like, hey, Sidekick, like, find me every customer that is buying these three products.

**Ben** · `41:01`
Mhm.

**Zach** · `41:06`
or sorry, like buying these, yeah, buying these three products. All right, they're buying pool tables, they're buying, you know, cue sticks, and they're buying cloth. Okay, great. Now find me all of the customers that are only buying pool tables and cue sticks. And now cross-reference that, so like show me all of the customers that just...are buying both of these things but aren't buying cloth. And boom, it gives you it in real time. Like here are, this is a perfect example of.These are call all these customers that aren't buying cloth and saying, I've got a bunch of customers that are buying pool tables and cues and as well as cloth. Let's talk about cloth. Like it's helping you identify patterns, right? And it's probably the same thing with like your point of door-to-door salesmen. Like door-to-door salesmen didn't just sell top probably one thing. Like we sold vacuums, right? And they probably had two or three different.

**Ben** · `41:54`
Be.

**Zach** · `42:04`
Vacuums, a good, better, best.

**Ben** · `42:06`
Mm-hmm.

**Zach** · `42:07`
They knew when they pulled into town, they walked up and down those streets and they saw those cars in the driveway. They knew before they got to that front door, which one they're going to pitch. That's A four-year-old car. That's a brand new Cadillac. Okay, I know I'm going to sell them the good one for the four-year-old car.

**Ben** · `42:16`
which one they would sell.Mhm.Yeah.

**Zach** · `42:27`
and I'm gonna push the best one for the Cadillac buyer. Like, and that's one point of data, right? And they probably looked at, how is the grass? Is the grass cut?

**Ben** · `42:37`
Yeah.Mhm.

**Zach** · `42:43`
Like, that's really ******* cool. Like, I really dig that. Like, even if you're just looking at, like, we're going to figure out demographic information, like, you know, just because it's a commercial location, you know, a commercial location in, I don't know, you know,

**Ben** · `42:46`
Yeah.

**Zach** · `43:03`
You know, we visited Delray Beach, Florida last year, just we needed to get out of the cold. And it's between, it's between, you know, wherever Trump is, Palm,

**Ben** · `43:07`
It.Our logo, Palm Springs.

**Zach** · `43:17`
Yeah, Palm Springs, yeah, not Palm Springs, but yeah, Palm Beach, Palm Beach and Boca Raton, Delray Beach is right in between, and you know, but again, like photo booth, any of this stuff, it's disposable income, so we know where to look, like we, we, we need that information, we should be using that information, like I know, and then...

**Ben** · `43:23`
Yeah.Yeah.

**Zach** · `43:39`
One of my son's buddies, his dad grew up outside of Miami and his father's house, and they were like describing it. They were actively like, it's like a demilitarized zone. Like you don't want to go there. It's like, okay, we know not to put a photo booth there, but we know to put a photo booth in Delray Beach. Like we're just having these targets. I think it's such a powerful tool.

**Ben** · `43:51`
Yeah.

**Zach** · `44:00`
where you're just not spinning your wheels, you know, as a salesperson.

**Ben** · `44:04`
Mhm.

**Zach** · `44:07`
Because, you know, a bar or whatever could have a ton of foot traffic, but they're having a ton of foot traffic for $2 beers. Like, we want to be in places that are selling $15 cocktails, $20 cocktails. Like, it's just the way it is, right? So, sorry, I get excited about this stuff. So I apologize for your, if you're

**Ben** · `44:21`
Mhm.It.No, it gives it gives me a lot to think about.

**Zach** · `44:29`
If it's not interesting, but...Yeah, there's just a lot of different ways to skin a cat, right? Or, you know, we're just building. Ultimately, this is just about building a better mouse trap.you know, if it's a matter of like your tools are going to help sniff some things out and then ultimately manage those. Because I think the biggest mistake, and I know John has said this or it's and it's true of any of any business is like,Once you have, once you reel that fish into the boat, once you get that customer on the line, like, you still, like, it's people forget to maintain that relationship.And so a tool like yours...or a tool like what maybe what we build to help a salesperson just remember to do it.

**Ben** · `45:21`
Yeah.

**Zach** · `45:21`
Just remember, like it's so important. And who knows where it leads, right? Like, so anyway.Um...So you just, you built this, but it's, you're saying it sits on top of Salesforce or it can, is it grabbing?

**Ben** · `45:40`
No, it's a standalone project, but it's also, it's able, like I can create as many connectors as I'd like to configure into it. So currently there's Gmail and there's Slack.

**Zach** · `45:43`
Okay.

**Ben** · `45:54`
So, should you have, like, should you have a door or a knocking service that all communicates on Slack, it'll it'll populate through that, so, like, you can use the API of Salesforce to integrate and pull from specific databases, and that's where I envisioned it integrating with Betson.

**Zach** · `45:59`
Outlook.Okay.Yeah.

**Ben** · `46:13`
but they're so slow with the Salesforce recreation. So I have no idea how that's going to work currently.

**Zach** · `46:21`
Well, you might not even need it because if it's a kind of a standalone, and I would think like if we built this specifically for like the photo booth project, Joe Camarota, Joseph Camarota, sorry, I keep saying that, Joseph Camarota showed me

**Ben** · `46:36`
Mhm.

**Zach** · `46:39`
showed me the Apple dashboard.the company of Apple that builds the photo booths. He showed me the dashboard. It was pretty slick.You know, it was a lot of information.Have you ever seen it?

**Ben** · `46:58`
No, I'm looking it up right now. The Luma Booth event photo dashboard. Oh, wait, no, that's not it.

**Zach** · `47:01`
So...Yeah, well, I don't know what it's called. I mean, it's Apple Industries. They're out of Long Island. You can go to the website, but Camarota showed me the back end and he's, I think they're only operating like two or three of them. It's very minimal, but like it's, you know, it's what you'd imagine. Dashboard, here are your three. These are the types of photo booths.this is the location and then you could click into them and it gave you all the vital stats. It would tell you, like we looked at one that was offline because he knows that location's closed, so the power's off. But once the power goes on, the modem hooks up and it gives him an up-to-date, like the last time it was connected, everything.The entire booth was working. It said it was working, you know, it was green, green lights across the board. It knew exactly how much paper it had. It knew how many Vens it had left. It could tell you the ink, the ink percentages, like all of that information that you're going to want to use.

**Ben** · `47:59`
Yeah, that's all the KPIs that you need.

**Zach** · `48:04`
Right? But that's what's cool too, which I don't think they really do right now. So in that back end...You or I could go in and put in, like...You know.Monday through Thursday.From...Ten to 10, that's the hours, operating hours. We're charging 5 bucks, 5 bucks for a photo booth.

**Ben** · `48:26`
Mhm.

**Zach** · `48:31`
Friday and Saturday night after 8 P.m. That $5 goes to $8 or just goes to $6, whatever. And then it goes back. And that's just that'll automatically happen. But that's where something like right now.

**Ben** · `48:43`
surge pricing.

**Zach** · `48:49`
AI isn't doing anything, right? It's just manual and you have to remember to do it or you set it and you kind of set it and forget it and this and that.

**Ben** · `48:56`
You want the kind of Walmart, you want the Walmart functionality where it has electronic pricing and it has surge pricing within a certain time.

**Zach** · `49:06`
I want surge pricing. I want it to be smart enough. I want it to be smart enough that there's a photo booth outside of Fenway Park. I want the booth to know when the socks are in town. I want it to know it's a 3 o'clock game.

**Ben** · `49:07`
Okay.

**Zach** · `49:21`
I wanted to know that there's a Noah Kahn concert going on at Fenway. I wanted to know these things and do surge pricing accordingly. Like, that's cool.

**Ben** · `49:33`
I think this is all within grasp. I just looked into it and the Apple Industries uses a couple programs for their external dependencies. So you can't just use an API from them directly, but they do offer proprietary software. For example, I don't know if Joseph showed you the out of booth experience.application or the Smile OS software API, but that's the back end that feeds into probably, like he probably showed you one of these softwares if it was about the photo booth, but all of this is able to be configured and I can add.

**Zach** · `49:58`
I don't think so.Okay.

**Ben** · `50:12`
I can pull the data from their website into this one.

**Zach** · `50:17`
Yeah, and again, like, I do need to remind myself, and I'm sure Mike will remind me as well. I mean, Mike, I mean, we get carried away with all of this stuff.

**Ben** · `50:24`
To hedge your expectations, yeah.

**Zach** · `50:26`
Well, yeah, but also too, like at the end, like for right now, for the next six months, like I just need to sell photo booths, right? Just in the traditional fashion, right? Like I need to find the location, place a photo booth, work with Catherine, get the, you know, get the contract signed and, you know, yada, yada, yada. But all of these things, like, that's just where my

**Ben** · `50:33`
Yeah.Mhm.

**Zach** · `50:48`
Mind goes with.

**Ben** · `50:49`
No, and it's okay. It keeps you, it keeps you motivated to keep kicking that can. Like that's what you need.

**Zach** · `50:53`
Yeah, well, I mean, I'm just thinking about the half a dozen different ways I could, you know, I'd want to place a photo booth. Like, I think there's opportunities to place photo booths in places that don't actually charge money to use it. And we still make money, you know, just marketing, marketing, you know, stores, retail stores, you know,places that are excited to have customers try something on or just get in there, take a picture, tag the location, and...you know, and it's a social media place, it's a marketing play, and they give us $1000 a month.You know, they pay, you know, they give us 1000 bucks a month and they pay for the paper and the ink. And they're thrilled because they've got their target audience, their demographic that they're looking for, running into the photo booth, taking pictures with their friends and posting it to whatever, you know. Anyway, it's a...No, it's cool.I would love to try to help you build, you know, I mean, you and I help each other and build and build something out like that specifically, again, like that's what's interesting, building something that's specifically designed for the use. Like I don't want a Swiss, I don't want a Swiss army knife because that's what all everything else.

**Ben** · `52:00`
Yeah.The form fit, yeah.Mhm.

**Zach** · `52:15`
feels like. Everything else, they try to sell you a Swiss Army knife. And it's like, I just need a ******* knife. Like, I don't need scissors and a magnifying glass. Like, I just need this thing to work for me. So if we could try that as like a proof of concept, like...

**Ben** · `52:16`
Yeah.Mhm.Yeah.

**Zach** · `52:34`
Yeah, that'd be sounds awesome.

**Ben** · `52:37`
One thing before we kind of cut it off or, you know, get on with our day. I have a project that I'm doing for school. It's like I'm starting a business just for a class. And there's this feature that I have.where essentially the business is, I use a brain encoding model and I use it to grade content based on how your brain would interpret it. And while people use the media or like they upload the media to grade their video, they have to wait for like 5 minutes. And it's just currently, it's like they just look at the spinning circle.But right now, I'm testing out the functionality of adding a chat bot where it's not as like you can ask ChatGPT anything, but it would, it would, it would ask, or it would, it would, it would have the context of the database that that user used, so their experience, how long they've been there.what they're doing and that would drive their experience. So...Essentially with the CRM, say you have a sales guy in there or you or like you have another seat. Should they want to request some data, they can just talk to this chat bot instead of having all these bells and whistles. I mean, the bells and whistles would be there, but they would be housed.Um...Under priority of the the chat bot, which you would you would want to interact with to to make the experience easier.

**Zach** · `54:12`
Hmm, okay. I'm not sure if I'm following you all the way, but are you asking me to like, are you asking me to play with it?

**Ben** · `54:16`
So, for example, the...Well, I mean, a little bit, like if I'm to implement this feature into here and say when you're starting out, you have like this many leads and you have all of this information filled out about all these things and you don't really feel like retrieving it.

**Zach** · `54:30`
Mhm.

**Ben** · `54:34`
If I have all that stored into a centric database for you to query, for you to talk to this chat bot and get like, for example, in your banking app, whatever you use, you can probably ask its AI question, how much money have I spent in this month or this timeframe to this timeframe? And it'll tell you.

**Zach** · `54:52`
Right.Right.

**Ben** · `54:54`
So instead of you having to manually go and retrieve all of that information that has been auto attributed to whatever object or whatever, you know, deal, you could just ask it. So say you're in a pinch, you're on the phone, you're like, oh ****, I don't know, I don't know, I don't know this piece. And then you can just type it in.

**Zach** · `55:13`
Sure. Yeah, yeah.

**Ben** · `55:14`
Like monkey, monkey love tool, monkey, monkey, monkey would love to have it an even smarter tool than than it has.

**Zach** · `55:20`
Sure, yeah. Monkey want harder rock. Yeah, no, it's no, it's true. Yeah, yeah, yeah, yeah. I mean, I think that's what was that's what was really cool. I mean, it's maybe it sounds similar, maybe it's not, but that's what was really neat about having Sidekick live in Shopify and

**Ben** · `55:24`
Yeah.

**Zach** · `55:39`
I still needed to check its work, but like I could ask it for like all of the data was there. I just didn't want to go find it, right? Like, like.

**Ben** · `55:47`
Mmh.

**Zach** · `55:50`
Tell me, you know, our top three states that we're shipping into. What are those, what are the top items in those states? Like having an AI built on top of a lot of this, a lot of this information, just even just simple sales information. Like how many customers do we have whose name is John?

**Ben** · `55:58`
Yeah.Yeah.

**Zach** · `56:10`
Like, it would find it. How many customers, like, who, what's, how many customers is today their birthday? Like, all of these things, like, it's...It's incredibly powerful. It's a beyond powerful tool. But you, the trick is...

**Ben** · `56:24`
Mhm.

**Zach** · `56:29`
The trick is...is that the person, it's like anything. It's, you know, garbage in, garbage out, right? It's the person that's using it. It's the person, it's, there's still, and I don't mean, I'm not like tooting my own horn or anything. There's still a, there's still a creativity required to ask those questions, right? Because

**Ben** · `56:38`
Yeah.

**Zach** · `56:52`
people that ask questions are typically inherently creative. And so you do need, you do need to like, I hadn't thought about it that way. Like that's where like my wife who works for Dell, and she's talking, we're talking about all this and how obviously everything's changing with them, is you have to be, you have toAt some point, tell your, you know, your agent, your AI agent, like, be a thought partner with me.

**Ben** · `57:20`
Mhm.

**Zach** · `57:21`
like understand how I'm using it. You're more powerful to me if you can help me think of ways I'm not using it. And also having the patience to be like, yeah, like having the patience to tell it like, nah, you're, I mean, I see where you're going with it. I just think you're off base and explain to it why.

**Ben** · `57:29`
Yeah, the gap analysis.

**Zach** · `57:41`
Like I don't mind doing that. Like I have conversations with my with my ChatGPT, like when we're when we're working on a project and we're doing something like you're off base there. This is why this is why this is really what I'm going for. And of course it like strokes your ego. It's like, that's genius. Like, all right, shut up. Like, **** ***. Like, I don't, I should actually tell it to stop.

**Ben** · `57:41`
Yeah.Mhm.People people think that loop is people think that loop is so ridiculous. Like I've been using AI since 2018, 2019 when it was like really awful. Where if you're having eloquent conversation and you're treating it as if it was an employee or like a coworker and you're giving it all of the context that's need it needs for the task that you are requiring of it.It's so much more capable than people had thought for like the longest time. So I think with that instruction built into the chat bot feature, which I can train the model, that's kind of my specialty. I think this could be a really viable product for Betson. And I didn't.

**Zach** · `58:25`
Totally.

**Ben** · `58:40`
I didn't foresee this going this direction. Like I was hired as an intern to streamline the CAD process. And that was, you know, to be frank, ***. That was, it was terrible. Dave left and he was disgruntled and the process was terrible, but I didn't know how bad the sales force was or how tangled up it was. And

**Zach** · `58:53`
Yeah.

**Ben** · `59:03`
As soon as I learned that, I kind of had to hedge my expectation when it came to, oh, I'm not actually going to be able to do anything with my skill set here. And now I think that I could.

**Zach** · `59:14`
Yeah, yeah, I mean, we should try because again, like if we could build something, like, I mean, again, this is, you know, this is day five for me, right? So at day 50 or even, I mean, even, I mean, 500, right, a year and a half from now, you know, I'm on.Like, at what point, like, what with these tools, like...how productive, how lucrative, how many units can we sell with like, you know, calling myself like a one man band, right? Like at some point I'll hit that, that.

**Ben** · `59:49`
Mhm.

**Zach** · `59:52`
Breaking point of like I can't take like this system is working so well. I have15 half hour calls every day for the next three weeks, right? Like at some point, like we will need another human being. But like where is that? And how many of these deals could we potentially close where?I don't need to get on the phone or get on the video. I mean, I can't imagine very many because people still, I'd like to think people still want.

**Ben** · `1:00:18`
Yeah.They like the human.

**Zach** · `1:00:26`
Right, but if we if we could do our job and get to the point from a marketing perspective, providing marketing materials, providing video content, providing like providing the right messaging to the right people, like there is a possibility, like they're not.

**Ben** · `1:00:41`
Mhm.

**Zach** · `1:00:43`
They're not handing over any money.right? Our website, Betson's been around for almost 100 years. Video, LinkedIn, like, okay, this is a real company. This is a real person. Like, maybe it can be done over e-mail. Or maybe it is like.you know, an e-mail sequence that's just like, all right, like I just emailed you the pitch deck. I didn't e-mail the pitch deck. Like, let me know what you think. And if you'd like to get on the phone or like to do a Zoom call, let's, you know, just click the link and schedule with me and I'm happy to jump on a call with you.And then at least I know. But I mean, at some point, there are going to be deals that are, we never meet.

**Ben** · `1:01:26`
Absolutely, like the the the choice of linguistic is gonna be big there.

**Zach** · `1:01:27`
We never talk, and it's not that it's a goal.Yeah, I mean, yeah, and again, like, I don't mind. I love talking with, like I told you, like, that's why I think I am hopefully like a pretty decent salesman is because I have an authentic interest in all of these different kinds of businesses, right? Whether you're, you know, the Death Museum in New Orleans or a little bar in, you know, San Diego or a truck stop in Spokane, like,

**Ben** · `1:01:48`
Thank you.

**Zach** · `1:01:54`
I'm authentically interested in like meeting people and learning about their business. So that does help. But I mean, if volume is, again, maybe volume isn't the goal, it is still quality over quantity. And that is where, you know, I'm usually also pretty decent at reading people. And so it's just like, I...

**Ben** · `1:02:07`
Yeah.Yeah.I think.I think before you put yourself in the field as much as you love to, I think having your expertise within the field of selling and talking to people enough to understand what makes them bite or what's driving them, I think

**Zach** · `1:02:15`
No, it's cool.

**Ben** · `1:02:34`
having your experience and having your input on how to, you know, make that happen without the human in the loop would be way more valuable in terms of training this.

**Zach** · `1:02:43`
It could be interesting, yeah. I mean, especially when, you know, even with HubSpot and knowing, you know, I don't, we never got into like the real nitty gritty, but like, how long did somebody open the emails? Like, I mean, HubSpot was cool because based on...past data like and I knew like if I didn't want to send it right now, if I didn't want to send an e-mail right now because I didn't want to be creepy, I would say like send later. It would actually make a suggestion of the it knew that this person and opened emails before 8 A.m. or.If it was an owner, like a construction company, the owners always, because they're on the job site first thing in the morning, they, it knew, send it after 3 P.m. So it's at the top of their inbox. Like if we could start getting into information, like how long did they spend looking at our e-mail? Did they click the link to go to the website?

**Ben** · `1:03:29`
Sure.Yeah.

**Zach** · `1:03:37`
Like, and I, and at this point, like, I don't even know what website you'd send them to.

**Ben** · `1:03:42`
Mhm.

**Zach** · `1:03:42`
Like, we don't want to send them to the Betson website, or we want to send them to a page on the Betson website that, in my opinion, currently does not exist.

**Ben** · `1:03:51`
Yeah, so like configuring that is...is on the railway of implementation, I'd say. Like building applications into the Betson website is kind of hard. What I've done previously is I've just made it on my own standalone and then I'd give it to the IT team and then they'd implement it. And it's still pretty slow. So I think it's going to be nice to have this idea going so we can keep it on the on the.

**Zach** · `1:03:58`
Yeah.Yeah.

**Ben** · `1:04:19`
On the horizon.

**Zach** · `1:04:20`
Yeah, I think like, you know, in my opinion with all of this, like, you know, you and I can keep chatting about Star Trek technologies, but like for right now, like, let's keep it simple, you know, like, you know, because the last thing we want to do, it's like, you know, it's like boiling a frog, you know, you just, you know, you heat it up slowly. You can't just throw a frog into boiling water.

**Ben** · `1:04:32`
Yeah.

**Zach** · `1:04:41`
That's when they just, have you heard that term?

**Ben** · `1:04:44`
No, dude, as soon as I got into the corporate field, I've gotten exposed to so many of these stupid...

**Zach** · `1:04:49`
Well, the boiling the frog thing, I will say, I was in a car with a bunch of buddies one night and I've got some buddies that are pretty smart guys and they do pretty well for themselves. And I'm sitting in the car and I have this buddy, Big Dave. He was the CFO of Shark Ninja for a while and great guy. And we're driving through Vermont. He's up visiting.And I'm driving down and I was like, I was like, Dave, it's like boiling a frog. He's like, he's got this weird accent. He's from a part of Canada. He's like, kid, what are you talking about? What about a frog? I was like, like boiling a frog, Dave. And he's just like, and I told him, I was like, so you can't cook a frog. You got to like put the frog in regular water and then you heat it up and the frog will stay there and die.

**Ben** · `1:05:26`
Mmh.

**Zach** · `1:05:29`
even if once it gets to boiling, it'll still just stay there because it's just acclimated, right? Versus throwing a frog. He's like, God, kid, I've never heard that before. That's dumb. He's like, the frogs are dumb. I'm like, all right, whatever. But yeah, I like, I probably liken new ideas at Betson to, you can't throw a frog, you can't throw them into boiling water.

**Ben** · `1:05:32`
Yeah, it's like a jacuzzi.Yeah.

**Zach** · `1:05:48`
Right, because there's this is this is scary. So yeah, keep it simple. Keep it simple to start. But anyway, cool, man. I don't know. Where do we go from here?

**Ben** · `1:05:49`
Yeah.Um, I'm gonna take what we're...

**Zach** · `1:06:03`
Because I don't want to, I can't tell you to do something. You're not my intern. And like, we...

**Ben** · `1:06:08`
No, I'm going to work on this. The stuff I have going currently, like the game room twin and the wizard, I have delegated a couple tasks out before I can continue implementation on that stuff. So what I'm going to do is I'm going to take the transcript from this meeting, ingest it, and...Apply this to all of the the the the CRM schema and see see what it changes, see what um.See what ideas this generates and I'll probably shoot you another message.

**Zach** · `1:06:41`
Yeah, okay, cool. Yeah, man, so I was just thinking too about like having this ability and all these things like we could actually do like AB testing on like marketing materials. That's freaking cool. I like that a lot. That's neat. All right, anyway, I gotta run. Have a great night. Take it easy. All right, we'll be in touch.

**Ben** · `1:06:51`
Yeah.Awesome. You too, Zachary.
